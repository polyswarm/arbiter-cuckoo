// dependencies
const chalk = require('chalk');

// will hold all results and gets breaked down in the terminal after
// testing completes.
let log = [];

// require all the test functions that need to be tested, and execute them
// in order, pushing the results into the 'log' array.
const evaluations = [
  require('./include-as-module')
].forEach(test => {
  log.push(test());
});

// display the results for each test in the terminal.
log.forEach((result, i) => {

  let title = result.title;
  let messages = result.messages;

  // display the title
  console.log(chalk.yellow(`test ${i+1}: ${title}:`));

  if(result.passed) {
    // if no message, the test succeeded
    console.log(chalk.green(`\t ✔ Succeed`))
  } else {
    messages.forEach(msg => {
      console.log(chalk.red(`\t ✘ ${msg}`));
    });
  }

});
