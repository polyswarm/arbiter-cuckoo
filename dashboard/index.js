const fs = require('fs');
const extend = require('deep-extend');
const parseArgs = require('minimist');

let _cmd = parseArgs(process.argv, {});
let singleRun = (_cmd.scripts || _cmd.styles || _cmd.build) == true;
let wasRequired = !(require.main === module);
let isBuiltLegacy = fs.existsSync('./tooling/build');
let forceBabel = _cmd['force-babel'] === true;
let tooling;

if(isBuiltLegacy && !forceBabel) {
  // source code has been built
  tooling = require(__dirname + '/tooling/build');
} else {
  // source code has not been built - use babel-node to run.
  require('babel-register');
  tooling = require(__dirname + '/tooling');
}

// formatting the config from json to a default set of config
// ensures that the system won't fail on missing configuration
// keys. If you add features, make sure to add the options to the
// default stack along any other modifications to that content
// if neccesary.
// const CONFIG_JSON = require('./config.json') || {};
const CONFIG_JSON = JSON.parse(fs.readFileSync('./config.json', 'utf-8'));

//
// default configuration
//
const CONFIG_DEFAULT = {
  "babel": {
    "path": "src/scripts",
    "file": "index.es6",
    "output": "/build/main.js",
    "browserify": {},
    "babel": {}
  },
  "sass": {
    "path": "src/styles",
    "file": "main.scss",
    "output": "build/css/styles.css",
    "sass": {}
  }
}

//
// result configuration after extending the json onto the option stack.
// CONFIG is globally accesible by all modules.
//
const CONFIG = extend(CONFIG_DEFAULT, CONFIG_JSON);

if(wasRequired) {

  // expose some tech from package
  module.exports = tooling;

} else {

  if(!singleRun) {

    tooling.start({
      config: CONFIG,
      development_mode: _cmd.development
    });

  } else {
    if(_cmd.styles) {
      tooling.compileStyles(CONFIG.sass);
    }
    if(_cmd.scripts) {
      tooling.compileScripts(CONFIG.babel);
    }
    if(_cmd.build) {
      tooling.compileScripts(CONFIG.babel);
      tooling.compileStyles(CONFIG.sass);
    }

  }

}
