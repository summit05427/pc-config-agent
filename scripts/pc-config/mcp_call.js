// 最小 MCP stdio 客户端：initialize -> tools/call -> 结果写文件。
// 仅用于本地淘宝采集，路径可用环境变量覆盖，避免把机器路径写死。
const { spawn } = require("node:child_process");
const fs = require("node:fs");

const NODE = process.env.TAOBAO_NODE || "E:\\Nodejs\\nodejs\\node.exe";
const SERVER = process.env.TAOBAO_SERVER || "F:\\tools\\chengkit-taobao\\server.cjs";
const SERVER_DIR = require("node:path").dirname(SERVER);

const [toolName, argsFile, outFile] = process.argv.slice(2);
const toolArgs = JSON.parse(fs.readFileSync(argsFile, "utf8"));

const child = spawn(NODE, [SERVER], {
  cwd: SERVER_DIR,
  stdio: ["pipe", "pipe", "pipe"],
});

let buffer = "";
let stderr = "";
let done = false;

const timer = setTimeout(() => {
  if (!done) {
    fs.writeFileSync(outFile, JSON.stringify({ error: "timeout", stderr }, null, 2));
    child.kill();
    process.exit(2);
  }
}, 180000);

function send(payload) {
  child.stdin.write(JSON.stringify(payload) + "\n");
}

child.stderr.on("data", (chunk) => {
  stderr += chunk.toString();
});

child.stdout.on("data", (chunk) => {
  buffer += chunk.toString();
  let index;
  while ((index = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, index).trim();
    buffer = buffer.slice(index + 1);
    if (!line.startsWith("{")) continue;
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      continue;
    }
    if (message.id === 1) {
      send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });
      send({
        jsonrpc: "2.0",
        id: 2,
        method: toolName === "__list__" ? "tools/list" : "tools/call",
        params: toolName === "__list__" ? {} : { name: toolName, arguments: toolArgs },
      });
    }
    if (message.id === 2) {
      done = true;
      clearTimeout(timer);
      fs.writeFileSync(outFile, JSON.stringify(message, null, 2));
      child.kill();
      process.exit(0);
    }
  }
});

send({
  jsonrpc: "2.0",
  id: 1,
  method: "initialize",
  params: {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "trae-stage9-harvest", version: "0.1.0" },
  },
});
