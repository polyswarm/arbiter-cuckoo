import {
  watch as watchStyles,
  compile as compileStyles
} from './lib/frontend-styles';

import {
  watch as watchScripts,
  transpile as compileScripts
} from './lib/frontend-scripts';

import FancyLogger from './lib/fancy-logger';

/* =============
  Tooling.welcomeMessage
  - shows a friendly welcome message to
============= */
function welcomeMessage(devMode = false) {

  const logger = new FancyLogger();
  let message = `watchers started - happy coding!`;

  if(devMode === true) message = `Running development mode and ${message}`

  logger.frame(message, {
    color: 'white',
    timestamp: false
  });

}

/* =============
Tooling.start
  - starts the watchers for sass and babel files
============= */
function start(api) {
  const sassWatcher = watchStyles(api.config.sass);
  const scriptsWatcher = watchScripts(api.config.babel);
  welcomeMessage(api.development_mode);
}

export {
  start,
  watchStyles,
  watchScripts,
  compileStyles,
  compileScripts
}
