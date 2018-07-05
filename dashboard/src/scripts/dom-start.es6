import $ from 'jquery';
import SVGLoader from './lib/svg-loader';
import stream from './lib/socket-handler';

// resolve handler shorthand
let _resolve = (_data = {}) => Promise.resolve(_data);
let _reject = (_err = {}) => Promise.reject(_err);
let resolveHash = (key, data) => {
  return { key, data };
};

// ajax request as a promise
let request = (url = '', method = 'GET', label = '') => new Promise((resolve, reject) => {
  $.ajax({
    url,
    success: response => resolve(resolveHash(label, response)),
    error: errors => reject(errors)
  });
});

const Response  = {
  SKIP_SOCKET: window.location.href.indexOf('skip-socket') > -1,
  MESSAGE_TYPES: [
    'counter-errors',
    'counter-artifacts-processing',
    'counter-backends-running',
    'counter-bounties-settled',
    'wallet',
    'backends'
  ],
  HOST: window.location.host
};

const Processes = [];
const websocket = `ws://${Response.HOST}/kraken/tentacle`;

function bindLoaderAnimation(el) {
  let step = 0;
  setInterval(() => {
    el.find('i').removeClass('filled').eq(step).addClass('filled');
    step++;
    if(step > el.find('i').length-1)
      step = 0;
  }, 500)
}

// DomStart handler - called upon page init
export default function DomStart() {

  //
  // Bind loader epicness
  //
  Processes.push(new Promise((resolve, reject) => {
    $(".loading-component").each((index, el) => bindLoaderAnimation($(el)));
    resolve(resolveHash('loaders', 'loaders initialized'));
  }));

  //
  // Add async inline svg replacement so we can alter
  // svg easier with css.
  //
  Processes.push(new Promise((resolve, reject) => {
    SVGLoader.loadPlaceholders('[data-svg-src]')
      .done(svgs => resolve(resolveHash('svgs', svgs)))
      .failed(errors => reject(errors));
  }));

  //
  // Preload data on app init for the manual bounties and artifacts
  //
  Processes.push(request(`http://${Response.HOST}/dashboard/bounties/manual`, 'GET', 'manual-bounties'));
  Processes.push(request(`http://${Response.HOST}/dashboard/bounties/pending`, 'GET', 'pending-bounties'));

  //
  // Connect websocket stream
  //
  if(!Response.SKIP_SOCKET)
    Processes.push(new Promise((resolve, reject) => {

      let data = {};
      let needMessages = Response.MESSAGE_TYPES;
      let processedMessages = [];

      let allMessagesReceived = () => {
        let ret = true;
        for(let nmsg in needMessages) {
          if(processedMessages.indexOf(needMessages[nmsg]) == -1) {
            ret = false;
          }
        }
        return ret;
      }

      Response.stream = stream(websocket, {
        onmessage: response => {
          let r = JSON.parse(response);
          data[r.msg] = r;
          processedMessages.push(r.msg);
          if(allMessagesReceived()) {
            resolve(resolveHash('ws', data));
          }
        },
        onerror: () => reject('Websocket returned an error')
      });
    }));

  return Promise.all(Processes).then(results => {
    for(let r in results)
      Response[results[r].key] = results[r].data;
    return _resolve(Response);
  }).catch(err => {
    return _reject({
      err,
      message: 'very faulty'
    });
  });

}
