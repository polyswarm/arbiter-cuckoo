// import dependencies (listed in package.json -- dependencies)
import $ from 'jquery';
import Chart from 'chart.js';
import moment from 'moment';
import Handlebars from 'handlebars';
import pattern from 'patternomaly';
import '@fengyuanchen/datepicker';

// hold some global params for the app
const Application = {
  data: {},
  datepickerActive: false,
  artifactAPIUrl: 'http://bak.cuckoo.sh:9080/dashboard/charts/artifacts',
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
    `)(data)
  }
};

// create a handlebars method to return a percentage from two wholes (from/to)
Handlebars.registerHelper('percentage', (part, total) => {
  let ret = Math.ceil(part / total * 100);
  if(ret >= 90) ret = `<span class="danger">${ret}</span>`;
  return new Handlebars.SafeString(`${ret}%`);
});

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
    $("#wallet .amount-container > p.nct").contents()[0].data = shortValue(message.nct, 2);
    $("#wallet .amount-container > p.eth").contents()[0].data = shortValue(message.eth, 2);
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

  let renderChart = data => {

    let ctx = $canvas[0].getContext('2d');

    data = data.map(point => {
      return {
        x: moment.unix(point[0]).toISOString(),
        y: point[1]
      }
    });

    return new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          data: data,
          // backgroundColor: pattern.draw('diagonal', 'rgba(109,85,134,.6)'),
          backgroundColor: 'rgba(63,16,107,.7)',
          pointBackgroundColor: '#21073A',
          pointHighlightFill: '#FFF',
          pointHighlightStroke: '#DDD',
          pointBorderColor: '#21073A',
          pointStyle: 'circle',
          pointRadius: 1
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
              display: false,
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
        }
      }
    });
  }

  $.get(Application.artifactAPIUrl, response => {

    renderChart(response.data);

    if($el.hasClass('content-loading'))
      $el.removeClass('content-loading');
  });

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

      // message = JSON.parse(message);
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

}
