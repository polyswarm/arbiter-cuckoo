// import dependencies (listed in package.json -- dependencies)
import $ from 'jquery';
import Chart from 'chart.js';
import moment from 'moment';
import Handlebars from 'handlebars';
import pattern from 'patternomaly';
import '@fengyuanchen/datepicker';
import PageSwitcher from './lib/page-switcher';

// hold some global params for the app
const Application = {
  data: {},
  datepickerActive: false,
  // artifactAPIUrl: 'http://bak.cuckoo.sh:9080/dashboard/charts/artifacts',
  artifactAPIUrl: `http://${window.location.host}/dashboard/charts/artifacts`,
  chartInitialized: false,
  chart: undefined,
  settledBounties: [],
  noop: () => new Function(),
  templates: {

    // renders table overview of backends
    backends: data => Handlebars.compile(`
      <table class="table content-fit">
        <thead>
          <tr>
            <th class="name">Name</th>
            <th>CPU</th>
            <th>Disk</th>
            <th>Memory</th>
          </tr>
        </thead>
        <tbody>
          {{#each backends}}
            <tr>
              <td class="name">{{@key}}</td>
              <td>{{cpu}}%</td>
              <td>{{percentage diskused disktotal}}</td>
              <td><span>{{percentage memused memtotal}}</td>
            </tr>
          {{/each}}
        </tbody>
      </table>
    `)(data),

    // alternative template that just displays machine info
    performanceDisplay: data => Handlebars.compile(`
      <div class="erector-container">
        <div>
          <div class="erector">
            <div class="erector-fill">
              <div class="erector-value" style="height: {{cpu}}%;"></div>
            </div>
            <h4>cpu <span>{{cpu}}%</span></h4>
          </div>
          <div class="erector">
            <div class="erector-fill">
              <div class="erector-value" style="height: {{memory}}%;"></div>
            </div>
            <h4>memory <span>{{memory}}%</span></h4>
          </div>
          <div class="erector">
            <div class="erector-fill">
              <div class="erector-value" style="height: {{disk}}%"></div>
            </div>
            <h4>disk <span>{{disk}}%</span></h4>
          </div>
        </div>
        <h3>{{name}}</h3>
      </div>
    `)(data),

    // bounty UI
    verdictBounty: data => Handlebars.compile(`
      <article class="verdict-item" data-bounty-guid="{{guid}}">
        <header>
          <h2><strong>Bounty</strong> {{short-uid guid 5}}</h2>
          <ul>
            <li class="bounty-amount">{{amount}} <strong>NCT</strong></li>
            <li class="bounty-created">{{moment-from created}}</li>
          </ul>
        </header>
        <section class="verdict-artifacts">
          <ul class="summary-list">
            <li>{{num_artifacts}} artifacts</li>
            <li>{{#if truth_settled}}Settled{{else}}Unsettled{{/if}}</li>
          </ul>
          <div class="hidden-inactive" data-populate="artifacts">
            <!-- populates artifactVerdict -->
          </div>
        </section>
        <footer>
          <a href="load:{{guid}}">Artifact verdicts</a>
        </footer>
      </article>
    `)(data),

    // artifact verdict UI
    verdictArtifacts: data => Handlebars.compile(`
      {{#each artifacts}}
        <article class="artifact-details">
          <header class="artifact-details-header">
            <div class="icon"></div>
            <div>
              <h3>{{name}}</h3>
              <ul class="backend-resource-list">
                {{#each verdicts}}
                  <li>
                    <a href="{{meta.href}}" target="_blank"><i class="fas fa-file-contract"></i> {{@key}}</a>
                    {{{verdict-badge verdict}}}
                  </li>
                {{/each}}
              </ul>
            </div>
          </header>
          <h4>Expert Verdicts:</h4>
          <ul class="expert-verdicts">
          {{#each expertOpinions}}
            <li>
              <div>
                <h5>{{author}}</h5>
                <p>{{metadata}}</p>
              </div>
              <div class="verdict-badge-holder">
                {{{verdict-badge verdicts}}}
              </div>
            </li>
          {{else}}
            <li><em>No opinions</em></li>
          {{/each}}
          </ul>
          <ul class="verdict-artifact" data-artifact-verdict="{{hash}}">
            <li>
              <label for="select-{{hash}}-unsafe">
                <input type="radio" name="verdict-{{hash}}" id="select-{{hash}}-unsafe" value="true" />
                <p>unsafe</p>
              </label>
            </li>
            <li>
              <label for="select-{{hash}}-safe">
                <input type="radio" name="verdict-{{hash}}" id="select-{{hash}}-safe" value="false" />
                <p>safe</p>
              </label>
            </li>
          </ul>
        </article>
      {{/each}}
      {{#unless truth_settled}}
        <p class="explanatory">Select artifacts to mark safe or unsafe. Then click submit to settle this bounty.</p>
        <ul class="button-list">
          <li><button class="grey" data-ignore-bounty>Ignore</button></li>
          <li><button class="purple" type="submit" data-verdict-bounty>Submit</button></li>
        </ul>
      {{else}}
        <p class="explanatory">You settled</p>
      {{/unless}}
    `)(data)

  }
};

// create a handlebars method to return a percentage from two wholes (from/to)
Handlebars.registerHelper('percentage', (part, total) => {
  let ret = Math.ceil(part / total * 100);
  if(ret >= 90) ret = `<span class="danger">${ret}</span>`;
  return new Handlebars.SafeString(`${ret}%`);
});

// handlebars method to shorten an id
Handlebars.registerHelper('short-uid', (uid, len = 3) => {
  return new Handlebars.SafeString(`${uid.substring(0, len)}...${uid.substring(uid.length-len, uid.length)}`);
});

// handlebars method to display dates as '... from ...'
Handlebars.registerHelper('moment-from', (date = new Date()) => new Handlebars.SafeString(moment(date).fromNow()))

// handlebars method to render 'safe' / 'unsafe' badges in the ui
Handlebars.registerHelper('verdict-badge', (verdict = null) => {
  if(verdict instanceof Array) {
    return new Handlebars.SafeString(`<span class="verdict-badge ${verdict[0] == true ? 'unsafe' : 'safe'}"></span>`);
  } else if(verdict == null) {
    return new Handlebars.SafeString(`<span class="verdict-badge">unknown</span>`);
  } else if (verdict < 50) {
    return new Handlebars.SafeString(`<span class="verdict-badge safe"></span>`)
  } else {
    return new Handlebars.SafeString(`<span class="verdict-badge unsafe"></span>`)
  }

})

// bouncy bouncy microplugin
$.fn.Bounce = function(config = {}) {
  // configure some settings as an object + defaults
  let options = $.extend({
    speed: 500,
    delay: 150,
    from: 1,
    to: 1.05
  }, config);
  // render basic css props
  this.css({
    transform: `scale(${options.from})`,
    transition: `transform ${options.speed}ms ease-out`
  });
  // perform the bounce maneuver
  setTimeout(() => {
    this.css({
      transform: `scale(${options.to})`
    });
    setTimeout(() => {
      this.css({
        transform: `scale(${options.from})`
      });
    }, options.speed);
  }, options.delay);
}

// ajax request helper as a promise
let request = (url = '', type = 'GET', data = {}) => new Promise((resolve, reject) => {

  // stringify data before send
  if(data) data = JSON.stringify(data);

  $.ajax({
    url, type, data,
    dataType: 'json',
    contentType: 'application/json',
    success: response => resolve(response),
    error: errors => reject(errors)
  });
});

/*
  updates the wallet amount
 */
function updateWalletAmount(message) {

  // https://stackoverflow.com/questions/9461621/how-to-format-a-number-as-2-5k-if-a-thousand-or-more-otherwise-900-in-javascrip
  let shortValue = (number, precision) => {
    let abbrev = ['', 'k', 'm', 'b', 't'];
    let unrangifiedOrder = Math.floor(Math.log10(Math.abs(number)) / 3)
    let order = Math.max(0, Math.min(unrangifiedOrder, abbrev.length -1 ))
    let suffix = abbrev[order];
    return (number / Math.pow(10, order * 3)).toFixed(precision) + suffix;
  };

  let $el = $("#wallet");

  // if the wallet is set to display NECTAR, display NCT
  if($el.data('view') == "nct") {
    $("#wallet .amount-container > p.nct").contents()[0].data = shortValue(message.nct / Math.pow(10, 18), 2);
    $("#wallet .amount-container > p.eth").contents()[0].data = shortValue(message.eth / Math.pow(10, 18), 2);
  }

}

/*
  updates the different application counters
*/
function updateCounter(counterName, counterValue) {

  let $counter = $(`#${counterName}`);
  if($counter.length) {
    $(`#${counterName} .text-content`).text(counterValue);

    // hide the loader if it's showing
    if($("#current-processes").hasClass('content-loading'))
      $("#current-processes").removeClass('content-loading');

    $counter.find('svg:first').Bounce({
      to: 1.1,
      speed: 400,
      delay: 10
    });

  }
}

/*
  Creates tables from the backends message info for displaying
  machine statuses
 */
function tablizeBackends(backends) {
  let $machines = $("#machine-status section");
  let $table = $(Application.templates.backends(backends));
  $machines.html($table);

  if($("#machine-status").hasClass('content-loading'))
    $("#machine-status").removeClass('content-loading');
}

/*
  Creates performance charts / displays.
 */
function updatePerformanceCharts(data) {

  let $el = $("#memory-info");
  let $container = $el.children('section');

  // empty the container
  $container.empty();

  // render backend charts recursively
  for(let be in data.backends) {

    let backend = data.backends[be];

    let stats = {
      name: backend.name,
      disk: Math.ceil(100 / backend.disktotal * backend.diskused),
      memory: Math.ceil(100 / backend.memtotal * backend.memused),
      cpu: Math.ceil(backend.cpu)
    }

    // let $tmpl = $(Application.templates.performanceChart(backend));
    let $tmpl = $(Application.templates.performanceDisplay(stats));
    $container.append($tmpl);

  }

  if($el.hasClass('content-loading'))
    $el.removeClass('content-loading');
}

/*
  Renders a processed artifacts chart in the designated area
 */
function initializeArtifactChart() {

  let $el = $("#processes-archive");
  let $canvas = $('<canvas width="100%" height="100%" />');
  $el.find('section').append($canvas);

  let renderChart = (data) => {

    let ctx = $canvas[0].getContext('2d');

    data = data.map(point => {
      return {
        x: moment.unix(point[0]),
        y: point[1]
      }
    });

    let c = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          data: data,
          backgroundColor: 'rgba(63,16,107,.1)',
          borderColor: 'rgba(63,16,107,.7)',
          pointBackgroundColor: 'rgba(63,16,107, .5)',
          pointHighlightFill: '#FFF',
          pointHighlightStroke: '#DDD',
          pointHitRadius: 10,
          pointBorderColor: '#21073A',
          pointStyle: 'circle',
          pointRadius: 3,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: '#fff',
          pointHoverBorderWidth: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        legend: false,
        scales: {
          xAxes: [{
            type: 'time',
            display: true,
            time: {
              unit: 'day',
              displayFormats: {
                day: 'MMM DD YYYY'
              }
            },
            scaleLabel: {
              display: false
            }
          }],
          yAxes: [{
            autoSkip: true,
            ticks: {
              beginAtZero: true
            }
          }]
        },
        layout: {
          padding: {
            right: 10,
            top: 10,
            bottom: 10,
            left: 10
          }
        },
        tooltips: {
          callbacks: {
            label: Application.noop(),
            title: (tooltipItem, data) => {
              let item = tooltipItem[0];
              let date = moment(item.xLabel).format('MM-DD-YYYY hh:mm A');
              let total = item.yLabel;
              return `${total} artifacts processed at ${date}`;
            }
          }
        },
        elements: {
          line: {
            tension: 0.2,
            cubicInterpolationMode: 'monotone'
          }
        },
        hover: {
          onHover: function(e) {
             var point = this.getElementAtEvent(e);
             if (point.length) e.target.style.cursor = 'pointer';
             else e.target.style.cursor = 'default';
          }
       }
      }
    });

    return c;

  }

  let updateChart = () => {
    $.get(Application.artifactAPIUrl, response => {

      if(!Application.chartInitialized) {
        Application.chart = renderChart(response.data);
        Application.chartInitialized = true;

        if($el.hasClass('content-loading'))
          $el.removeClass('content-loading');

        return;
      }

    });
  }

  updateChart();

}

/*
  Generic handler for settling a bounty
 */
function bountySettleHandler(element, bounty) {

  if(!element) return;

  // action button
  let parent = element.hasClass('verdict-item') ? element : element.parents('.verdict-item');
  let submit = parent.find('button[data-verdict-bounty]');
  let ignore = parent.find('button[data-ignore-bounty]');

  let stateHandlers = {
    freeze: () => {
      // disables inputs / buttons
      parent.find('.verdict-artifact label').addClass('disabled');
      parent.find('.verdict-artifact label > input').prop('disabled', true);
      $(submit, ignore).prop('disabled', true);
    },
    unfreeze: () => {
      // enables inputs/buttons
      parent.find('.verdict-artifact label').removeClass('disabled');
      parent.find('.verdict-artifact label > input').prop('disabled', false);
      $(submit, ignore).prop('disabled', false);
    },
    done: () => {
      // pre-action handler
      parent.slideUp();
    },
    setPending: () => {

      parent.appendTo("#pending-bounties"); // swaps element to bounties-pending column

      // sets the element to pending
      parent.find('.button-list').hide();
      parent.find('.button-list').after($("<p class='indicate-settlement'><i class='fas fa-spinner-third fa-spin'></i>Settling...</p>"));

      let newTotalManual = parseInt($("#bounty-verdicts").find('#total-manual').text())-1;
      let newTotalPending = parseInt($("#bounty-verdicts").find('#total-pending').text())+1;

      $("#bounty-verdicts").find("#total-manual").text(newTotalManual);
      $("#bounty-verdicts").find("#total-pending").text(newTotalPending);
    },
    error: () => {
      // displays an error if there is an error
    }
  }

  // when the submit button is clicked, collect all results for the loaded
  // artifacts based on their occurance in the bounty to sent a list back
  // with the verdicts
  submit.bind('click', e => {

    let body = {
      verdicts: []
    };

    for(let a in bounty.artifacts) {
      let hash = bounty.artifacts[a].hash;
      let verdict = element.find(`input[name="verdict-${hash}"]:checked`);
      body.verdicts.push(verdict.val() == "true");
    };

    // freeze ui
    stateHandlers.freeze();

    request(`/dashboard/bounties/${bounty.guid}`, 'POST', body).then(response => {
      // store this bounty
      Application.settledBounties.push({
        guid: bounty.guid,
        callback: () => {
          stateHandlers.done();
          $("#total-pending").text(parseInt($("#bounty-verdicts").find('#total-pending').text())-1);
        }
      });
      stateHandlers.setPending();
    }).catch(err => console.error(err));

  });

}

/*
  A centralized function to format the artifact details stream
  - note => the input == the output
 */
function formatArtifactVerdicts(bounty) {
  // create list of relevant expert opinions to pass
  // to the template
  for(let i in bounty.artifacts) {
    let item = bounty.artifacts[i];
    item.expertOpinions = [];
    if(bounty.assertions instanceof Array) {
      for(let assertion of bounty.assertions) {
        if(!assertion.mask[i]) continue;
        item.expertOpinions.push(assertion);
      }
    }
  }
  return bounty;
}

/*
  Handler for showing/hiding artifact data
 */
function loadBountyArtifacts(guid, target) {

  let $artifacts = target.find('.verdict-artifacts');

  request(`/dashboard/bounties/${guid}`).then(data => {

    data = formatArtifactVerdicts(data);

    if(!$artifacts.hasClass('shown')) {
      let html = $(Application.templates.verdictArtifacts(data));
      target.find('[data-populate="artifacts"]').html(html);
      bountySettleHandler(html, data);
    }

    $artifacts.toggleClass('shown');
    target.find('footer > a[href^="load:"]').text($artifacts.hasClass('shown') ? 'Cancel' : 'Artifact verdicts');

  }).catch(err => console.error(err)); // <== do not forget to handle this in the frontend!
}

/*
  A function to spawn a bounty item
 */
function createBounty(bounty) {
  return {
    bounty, // stores the data object (obj.bounty)
    render: function() {
      return $(Application.templates.verdictBounty(this.bounty));
    }, // renders the bounty html
    init: function(container) {

      let el = this.render();

      if(container) {

        container.append(el);

        el.find('a[href^="load:"]').bind('click', e => {
          e.preventDefault();
          let guid = $(e.currentTarget).attr('href').split(':')[1];
          if(!guid) return false;
          loadBountyArtifacts(guid, el);
        });

      }

      return this;
    } // initializes everything
  }
}

/*
  Initializes the verdict UI
 */
function initializeVerdicts(manual, pending) {

  let bountyContainer = $("#bounty-verdicts");

  let bounties = {
    manual: [],
    pending: []
  }

  for(let bounty in manual)
    bounties.manual.push(createBounty(manual[bounty]));

  for(let bounty in pending)
    bounties.pending.push(createBounty(pending[bounty]));

  // populate list-totals
  bountyContainer.find("#total-manual").text(manual.length);
  bountyContainer.find("#total-pending").text(pending.length);

  for(let b in bounties.manual)
    bounties.manual[b].init(bountyContainer.find('#manual-bounties'));

  for(let b in bounties.pending)
    bounties.pending[b].init(bountyContainer.find('#pending-bounties'));

  // mock for aesthethics
  setTimeout(() => {
    bountyContainer.removeClass('content-loading');
  }, 1000);

}

// DOMReady handler
export default function DomReady(app = {}) {

  Application.data = app;

  // initialize datepickers within .filter elements
  $(".filters [data-toggle='datepicker']").datepicker({
    autoPick: true,
    autoHide: true
  }).on('show.datepicker', e => {
    Application.datepickerActive = true;
  }).on('hide.datepicker', e => {
    Application.datepickerActive = false;
  });

  // handle focussed content fields
  $("div.content.hover-resize")
    .on('mouseenter', e => $(e.currentTarget).addClass('content-focus'))
    .on('mouseleave', e => {
      if(!Application.datepickerActive)
        $(e.currentTarget).removeClass('content-focus');
    });

  // attach message handler to active stream and hook them to their
  // UI components
  if(Application.data.stream instanceof Object) {

    let socketHook = message => {

      // in case of message being a string, parse it to json
      if(typeof message === 'string')
        message = JSON.parse(message);

      let type = message.msg;

      switch(type) {
        // if the message is for the wallet, update the wallet value
        case 'wallet':
          updateWalletAmount(message.wallet);
        break;
        // if any of these are the message, update the corresponding element
        case 'counter-bounties-settled':
        case 'counter-artifacts-processing':
        case 'counter-backends-running':
        case 'counter-errors':
          updateCounter(type, message[type]);
        break;
        // creates visual reflection of backend performance insights
        case 'backends':
          tablizeBackends(message);
          // updatePerformanceCharts(message);
        break;
        // when a pending bounty is settled, remove it from the UI
        case 'bounties-settled':
          let stopLoop = false;
          let targetBounty = message['bounties-settled'].guid;
          for(let b in Application.settledBounties) {
            if(stopLoop) return;
            if(Application.settledBounties[b].guid == targetBounty) {
              console.log(`Completed bounty ${targetBounty}`);
              if(Application.settledBounties[b].callback)
                Application.settledBounties[b].callback();
              Application.settledBounties.splice(b, 1);
              stopLoop = true;
            }
          }
        break;
      }
    }

    // append onmessage handler
    Application.data.stream.onmessage = socketHook;

    // pre-init app with initialized socket data
    if(Application.data.ws) {
      for(let d in Application.data.ws) {
        socketHook(Application.data.ws[d]);
      }
    }

  }

  // initialize the chart for the processed artifacts
  initializeArtifactChart();

  // trigger the verdict system init
  initializeVerdicts(Application.data['manual-bounties'], Application.data['pending-bounties']);

  // init the page-switcher modules automagically
  PageSwitcher.findAndBind($(".page-switcher"));

}
