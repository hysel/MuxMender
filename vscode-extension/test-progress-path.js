"use strict";
const assert = require("node:assert/strict");
const path = require("node:path");
const { decodeMediaPath } = require("./media-path");
const { createProgressParser } = require("./progress");
for (const value of [String.raw`Y:\TV\Star Trek\episode.mkv`, String.raw`\\truenas\Media\TV\Amélie + 100% #1 & 2.mkv`, "C:/test/video.mkv"]) {
  const encoded = Buffer.from(value, "utf8").toString("base64url");
  assert.equal(decodeMediaPath(new URLSearchParams(`file64=${encoded}`)), path.win32.normalize(value));
}
assert.equal(decodeMediaPath(new URLSearchParams('file=C%3A%2F100%2520percent.mkv')), 'C:\\100%20percent.mkv');
assert.throws(() => decodeMediaPath(new URLSearchParams('file=relative.mkv')));
assert.throws(() => decodeMediaPath(new URLSearchParams('file64=%%%')));
assert.throws(() => decodeMediaPath(new URLSearchParams('file64=_w')));
const values = [];
const parse = createProgressParser(x => values.push(x.increment));
for (const character of 'log\nMUXMENDER_PROGRESS=25\nMUXMENDER_PROGRESS=50\nMUXMENDER_PROGRESS=100\n') parse(character);
assert.deepEqual(values, [25, 25, 50]);
console.log('Path round-trip and chunked progress tests passed');
