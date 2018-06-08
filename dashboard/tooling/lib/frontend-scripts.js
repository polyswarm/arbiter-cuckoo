import fs from 'fs';
import path from 'path';
import browserify from 'browserify';
import exorcist from 'exorcist';
import chokidar from 'chokidar';

import FancyLogger from './fancy-logger';
import { util } from './utilities';

// create logger
const logger = new FancyLogger();

let messages = {
  compiled: (path, file, output) => {
    logger.frame(`${path}/${file} > ${output}`, {
      color: 'yellow'
    });
  }
}

// config creation shortcut
let createConfig = (options = {}) => Object.assign({
  path: null,
  file: null,
  output: null
}, options);

/*
  does a transpilation of a single entry file
 */
function transpile(options = {}) {

  // parse config
  let {
    path,
    file,
    output
  } = createConfig(options);

  // extract the babel/browserify options
  let _babel = options.babel || {};
  let _browserify = options.browserify || {};

  if(_babel.extensions) _browserify.extensions = _babel.extensions;

  return new Promise((resolve, reject) => {

    let b = browserify(util.cwd(`${path}/${file}`), _browserify);

    b.transform("babelify", _babel);

    b.on('bundle', function(bundle) {
      messages.compiled(path, file, output);
      resolve('Script transpiling done');
    });

    b.bundle()
      .on('error', function(err) {
        console.log(err.codeFrame);
        console.log(err.message);
        this.emit('end');
        reject(err);
      })
      .pipe(exorcist(util.cwd(`${output}.map`)))
      .pipe(fs.createWriteStream(util.cwd(output)));

  });

}

/*
  starts a watcher that will call transpile on file changes.
 */
function watch(options = {}) {

  // parse config
  let {
    path,
    file,
    output
  } = createConfig(options);

  return chokidar.watch(util.cwd(path)).on('change', (event, p) => {
    transpile(options).then(result => {
      // cycle done
    }, err => {
      console.log(err);
    })
  });

}

export { transpile, watch }
