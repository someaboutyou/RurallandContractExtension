
const fs = require('fs');
const content = fs.readFileSync(process.argv[2], 'utf8');
fs.writeFileSync(process.argv[3], content, 'utf8');
console.log('Done');
