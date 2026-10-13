const fs = require("fs");
const YAML = require("yaml");

const config = YAML.parse(fs.readFileSync(`${__dirname}/../config/http.yaml`, "utf8"));

module.exports = { config };
