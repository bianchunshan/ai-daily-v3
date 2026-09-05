const test = require("node:test");
const assert = require("node:assert/strict");
const { complete } = require("../lib/model");
const config = {
  provider: "kimi",
  style: "anthropic",
  url: "https://example.invalid",
  key: "test",
  model: "test",
};
test("Stream text and tool JSON are reassembled across split network chunks", async () => {
  const original = global.fetch;
  let request;
  const data = [
    {
      type: "content_block_start",
      index: 0,
      content_block: { type: "text", text: "" },
    },
    {
      type: "content_block_delta",
      index: 0,
      delta: { type: "text_delta", text: "正在查询" },
    },
    {
      type: "content_block_start",
      index: 1,
      content_block: {
        type: "tool_use",
        id: "tool1",
        name: "search_news",
        input: {},
      },
    },
    {
      type: "content_block_delta",
      index: 1,
      delta: { type: "input_json_delta", partial_json: '{"query":"英伟达"}' },
    },
  ]
    .map((d) => "data: " + JSON.stringify(d) + "\n\n")
    .join("");
  const bytes = new TextEncoder().encode(data);
  global.fetch = async (url, options) => {
    request = JSON.parse(options.body);
    return new Response(
      new ReadableStream({
        start(c) {
          for (let i = 0; i < bytes.length; i += 7)
            c.enqueue(bytes.slice(i, i + 7));
          c.close();
        },
      }),
      { headers: { "content-type": "text/event-stream" } },
    );
  };
  try {
    let output = "";
    const blocks = await complete(config, {
      system: "test",
      messages: [
        { role: "user", content: "first" },
        { role: "assistant", content: "answer" },
        { role: "user", content: "follow up" },
      ],
      tools: [],
      onText: (t) => (output += t),
      signal: AbortSignal.timeout(1000),
    });
    assert.equal(output, "正在查询");
    assert.equal(blocks[1].input.query, "英伟达");
    assert.equal(request.messages.length, 3);
  } finally {
    global.fetch = original;
  }
});
test("Invalid credential error is readable and never contains upstream secrets", async () => {
  const original = global.fetch;
  global.fetch = async () =>
    new Response("secret upstream diagnostics", { status: 401 });
  try {
    await assert.rejects(
      complete(config, { system: "", messages: [], onText: () => {} }),
      (e) => e.code === "model_auth" && !e.message.includes("secret"),
    );
  } finally {
    global.fetch = original;
  }
});
