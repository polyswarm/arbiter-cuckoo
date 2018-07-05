import fs from 'fs';
import sass from 'node-sass';
import chokidar from 'chokidar';
import parseSassMap from 'json-to-sass-map';
import YAML from 'yamljs';

import FancyLogger from './fancy-logger';
import { util } from './utilities';

// create logger
const logger = new FancyLogger();

let messages = {
  compiled: (path, file, output) => {
    logger.frame(`${path}/${file} > ${output}`, {
      color: 'blue'
    });
  }
}

/*
  Creates a configuration object
 */
let createConfig = (options = {}) => Object.assign({
  path: null,
  file: null,
  output: null,
  watchExtra: [],
  notifications: true
}, options);

/*
  Compiles the sass entry file to a css buffer and writes it
 */
function compile(options = {}) {

  let {
    path,
    file,
    output
  } = createConfig(options);

  let _sass = Object.assign({
    file: util.cwd(`${path}/${file}`),
    importer: []
  }, options.sass || {});

  // add required sourcemap properties if sourcemaps are enabled
  if(_sass.sourceMap === true) {
    _sass.outFile = util.cwd(output);
  }

  // hook in an extra-handy yaml importer to cross-reference style information
  // between the stylesheets and the other components of the frontend build
  // factory (like babel, django etc.) in a suited style like YAML (for aesthethics) :)
  _sass.importer.push((url, prev, done) => {

    let ext = util.extension(url);

    if(ext == '.yml') {
      YAML.load(url, result => {
        let flattened = JSON.stringify(result);
        let sassMap = parseSassMap(flattened);
        done({
          contents: sassMap
        });
      });
    } else {
      done({
        file: url
      });
    }

  });

  return new Promise((resolve, reject) => {
    sass.render(_sass, (err, result) => {
      if(err) {
        reject(err);
        return;
      } else {
        // write the css
        util.writeBuffer(util.cwd(output), result.css).then(() => {
          // if we have sourcemaps enabled, write that.
          if(_sass.sourceMap) {
            util.writeBuffer(util.cwd(`${output}.map`), result.map).then(() => {
              messages.compiled(path, file, output);
              resolve(result, `${path}/${file}`, output);
            }, err => {
              reject(err);
            });
          } else {
            messages.compiled(path, file, output);
            resolve(result, `${path}/${file}`, output);
          }
        }, err => {
          reject(err);
        });
      }
    });
  });
}

/*
  Watches the scss folder for changes
 */
function watch(options = {}) {

  let {
    path,
    file,
    output,
    watchExtra,
    notifications
  } = createConfig(options);

  let watchPaths = [util.cwd(path)];
  if(watchExtra) {
    if(typeof watchExtra === 'string') {
      watchPaths.push(watchExtra);
    } else if (watchExtra instanceof Array) {
      watchExtra.forEach(p => watchPaths.push(p))
    }
  }

  return chokidar.watch(watchPaths).on('change', (event, p) => {
    compile(options).then(result => {
      // cycle done
      if(notifications)
        util.notify('Sass compiled to css');
    }, err => {
      console.log(err);
      // cycle done
      if(notifications)
        util.notify('Sass: An error occured. See terminal for details');
    });
  });

}

export { compile, watch };
