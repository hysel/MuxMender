"use strict";

// Child-process stdout chunks may split markers anywhere, including in digits.
function createProgressParser(onProgress) {
  let pending = "";
  let last = 0;
  return (chunk) => {
    pending += chunk;
    const lines = pending.split(/\r?\n/);
    pending = lines.pop().slice(-4096);
    for (const line of lines) {
      const match = /^MUXMENDER_PROGRESS=(\d+(?:\.\d+)?)$/.exec(line.trim());
      if (!match) continue;
      const percent = Math.min(100, Number(match[1]));
      onProgress({ increment: Math.max(0, percent - last), message: `${percent.toFixed(1)}%` });
      last = Math.max(last, percent);
    }
  };
}
module.exports = { createProgressParser };
