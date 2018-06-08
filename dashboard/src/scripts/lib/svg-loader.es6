/*
  SVGLoader 0.1

  * dependencies: jQuery

  - finds all occurences of any HTML element containing `[data-svg-src]`
  - tries to load that svg
    - if sucessfull, injects that svg code after the placeholder
    - if unsuccessfull, handles that with caution and allows a custom callback
      for when it's very wishable to handle that error on the frontend (such as
      a respectable substitution fallback or whatever)
  - respects some configurables:

    - width: the width of the svg
      { width: Number } OR `<data-svg-w />`

    - height: the height of the svg
      { height: Number } OR `<data-svg-h />`

    - clickable: if the svg should be wrapped in an <a> tag
      { clickable: Boolean }

    - class: additional css class
      { class: String }]

    - can be run multiple times for different use cases that uses different configurations
    - is a chainable utility with optional callbacks for each step in the program:
      SVGLoader.load().loaded().done().failed()

  ### it still should:

  - detect live browser support for SVG and allow for a fallback for this browser,
    so that can be handled automatically. but not important for now.

  usage:

    ``` /index.html

    <span data-svg-src="/path/to/svg.svg" data-svg-w="16" data-svg-h="16"></span>

    ``` /main.js

    import SVGLoader from './lib/SVGLoader';

    SVGLoader.loadPlaceholders('[data-svg-src]', {
      width: 16,
      height: 16,
      clickable: false,
      class: 'my-class'
    }).then(result => {
      // any loaded single svg is passed here as jQuery object
    }).done(results => {
      // all loaded svg's are passed here as jQuery iterable
    }).failed(err => {
      // any errors for svg requests can be processed here
    });

    ```

 */

// dependencies
import $ from 'jquery';

// default options
const _defaults = {
  width: 16,
  height: 16,
  clickable: false,
  class: false
}

// syntactical pleasure: noop is an empty function :D
const noop = new Function();

// populates the svg, any rendering specific stuff
// is done here
function populate(result, options) {

  let width  = result.placeholder.attr('data-svg-w') || options.width;
  let height = result.placeholder.attr('data-svg-h') || options.height;

  result.svg.attr({
    width: width,
    height: height
  });

  result.placeholder.after(result.svg);

  // if these are 'buttons' (in the context way, they could be part of some
  // interaction), wrap these in an <a> tag.
  if(options.clickable) {
    result.svg.wrap('<a />');
  }

  // add a class if given in the configuration
  if(options.class) {
    result.svg.addClass(options.class);
  }

  result.placeholder.remove();
  return result.svg;
}

// load path with a promise
function load(path, placeholder) {
  return new Promise((resolve, reject) => {
    $.get(path, 'xml').done(function(response) {
      resolve({
        svg: $(response).find('svg'),
        placeholder: $(placeholder)
      });
    }).fail(function(err, xhr) {
      reject({
        err: err,
        xhr: xhr,
        path: path,
        placeholder: placeholder
      });
    });
  });
}

/*
  Utility for fetching SVG's
 */
class SVGLoader {

  static loadPlaceholders(selector, config = {}) {

    let options  = $.extend(_defaults, config);

    let promises = [];
    let loaded   = [];

    let chain = {
      _success: noop,
      _failed: noop,
      _done: noop
    }

    // preflight all results
    $(selector).each((i, placeholder) => {
      let src = $(placeholder).data('svgSrc');
      promises.push(load(src, placeholder));
    });

    // load + parse and fire the chained callbacks
    Promise.all(promises).then(results => {
      for(var r in results) {
        let parsed = populate(results[r], options)
        loaded.push(parsed);
        chain._success(parsed)
      }
      chain._done(loaded);
    }).catch(err => {
      chain._failed(err);
    });

    // callback chain for the actions:
    // `loaded`: 1 svg is done loading
    // `failed`: 1 svg failed loading
    // `done`: all svg's have done loading
    let chainable = {
      loaded: fn => {
        chain._success = fn;
        return chainable;
      },
      failed: fn => {
        chain._failed = fn;
        return chainable;
      },
      done: fn => {
        chain._done = fn;
        return chainable;
      }
    }

    return chainable;

  }

}

// export the class when requested as `import SVGLoader`
export default SVGLoader;

// export meta properties on the SVGLoader namespace
export { _defaults };
