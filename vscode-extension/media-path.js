"use strict";
const path = require("path");

// Base64url avoids URI/parser transformations of UNC backslashes, percent
// signs, plus signs, Unicode and spaces. Never repeatedly percent-decode paths.
function decodeMediaPath(parameters, key = "file") {
  const encoded = parameters.get(`${key}64`);
  let value = parameters.get(key);
  if (encoded !== null) {
    if (!/^[A-Za-z0-9_-]+$/.test(encoded)) throw new Error("Malformed encoded media path");
    value = Buffer.from(encoded, "base64url").toString("utf8");
    if (Buffer.from(value, "utf8").toString("base64url") !== encoded) throw new Error("Invalid UTF-8 media path");
  }
  if (!value || value.includes("\0")) throw new Error("Missing or invalid media path");
  if (!path.win32.isAbsolute(value)) throw new Error("Media path must be absolute");
  return path.win32.normalize(value);
}
module.exports = { decodeMediaPath };
