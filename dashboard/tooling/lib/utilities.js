import fs from 'fs';
import path from 'path';

class Utilities {

  // easy cwd mapping
  static cwd(file) {
    let dir = path.dirname(require.main.filename);
    return `${dir}/${file}`;
  }

  // mapping to a dependency in node_modules
  static dep(pkgPath = '/node_modules') {
    return Utilities.cwd(`node_modules/${pkgPath}`);
  }

  // quickly retrieve the extension name of a path
  static extension(url = undefined) {
    if(!url) return false;
    return path.extname(url);
  }

  // writeBuffer shortcut as a promise
  static writeBuffer(output, buffer) {
    return new Promise((resolve, reject) => {
      fs.writeFile(output, buffer, err => {
        if(err) {
          reject(err);
          return;
        }
        resolve({ output, buffer });
      })
    });
  }

  // utility for stripping out ugly '../' parts from paths.
  static prettyPath(pathString) {
    return pathString.split('/').filter(part => part.indexOf('..') == -1).join('/');
  }

  // returns if package has been called as a module or not
  // > says it's not by default. Make sure that the require object
  //   is passed as a param.
  static wasRequired(_req = undefined) {
    let isCLI = _req.main === module;
    return !isCLI;
  }

}

export { Utilities as util };
