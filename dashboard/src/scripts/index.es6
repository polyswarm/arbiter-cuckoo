// import modularized code
import DomStart  from './dom-start';
import DomReady  from './dom-ready';
import DomLoaded from './dom-loaded';
import DomError  from './dom-error';

/*
  document ready - verifies available 3rd party dependencies
  and executes domReady() function that will initialize the app.
 */

// call domstart - prerendering code can be executed
DomStart()
  .then(data => DomReady(data))
  .catch(err => DomError(err));

// hook in a handler for the DOMContentLoaded as well
document.addEventListener("DOMContentLoaded", DomLoaded);
