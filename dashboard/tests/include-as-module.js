// import the wcmp object to test against
const wcmp = require('../');

// defines what the 'wcmp' object should look like
const moduleSpec = [
  { key: 'start', type: Function },
  { key: 'watchStyles', type: Function },
  { key: 'watchScripts', type: Function },
  { key: 'compileStyles', type: Function },
  { key: 'compileScripts', type: Function }
];

// define the test function
module.exports = function test() {

  // default result object. Is received as result object in the general
  // test handler.
  let result = {
    title: 'WCMP constructor test',
    passed: true,
    messages: []
  }

  // define how to fail an entry
  let fail = (msg = '') => {
    result.messages.push(msg);
    result.passed = false;
  }

  // check if we have the constructor to start with, if not - fail the test.
  if(wcmp === undefined) {
    result.passed = false;
    result.messages.push('WCMP constructor resolves as `undefined`');
  } else {
    // loop through the spec object and compare each value with its type.
    for(let val in moduleSpec) {
      let entry = moduleSpec[val];
      if(wcmp.hasOwnProperty(entry.key)) {
        if(!(wcmp[entry.key] instanceof entry.type)) {
          fail(`WCMP.${entry.key} is not a ${String.name}`)
        }
      } else {
        fail(`Module requirement failed: missing key ${entry.key} in WCMP module.`);
      }
    }
  }

  // return only the results object - any test function should return the same
  // result object, an object with keys: 'title', 'passed' and 'messages'.
  // title => The title of the test
  // passed => Should evaluate true or false (true to succeed, false to fail)
  // messages => A list of error messages
  return result;

}
