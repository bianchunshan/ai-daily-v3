const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
test("Focused article is explicit; tools and conversation history reach the model", async () => {
  const store = require("../lib/news-store");
  const model = require("../lib/model");
  const originals = {
    readData: store.readData,
    article: store.article,
    complete: model.complete,
    configuration: model.configuration,
  };
  const focus = {
    id: "1234567812345678",
    title: "测试耳机",
    body: "这是指定文章正文",
    ts: "2026-09-05",
    url: "https://example.org/article",
  };
  store.readData = async () => ({
    data: { items: [{ id: "2222222222222222", title: "无关汽车资讯" }] },
  });
  store.article = async () => focus;
  model.configuration = () => ({ provider: "test", model: "test" });
  let captured;
  model.complete = async (c, args) => {
    captured = args;
    args.onText("指定文章的回答");
    return [{ type: "text", text: "指定文章的回答" }];
  };
  delete require.cache[require.resolve("../api/chat")];
  const handler = require("../api/chat");
  const res = new EventEmitter();
  res.status = () => res;
  res.json = (d) => {
    res.data = d;
  };
  try {
    await handler(
      {
        method: "POST",
        headers: {},
        socket: { remoteAddress: "test" },
        body: {
          question: "它的优势是什么",
          focusId: focus.id,
          history: [
            { role: "user", content: "测试耳机怎么样" },
            { role: "assistant", content: "与音频相关" },
          ],
        },
      },
      res,
    );
    assert.equal(res.data.answer, "指定文章的回答");
    assert.equal(captured.messages.length, 3);
    assert(captured.messages[2].content.includes("用户当前正在阅读"));
    assert(!captured.messages[2].content.includes("无关汽车"));
    assert.equal(captured.tools.length, 3);
  } finally {
    Object.assign(store, {
      readData: originals.readData,
      article: originals.article,
    });
    Object.assign(model, {
      complete: originals.complete,
      configuration: originals.configuration,
    });
  }
});
