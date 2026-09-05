function configuration() {
  const provider = (process.env.CHAT_PROVIDER || "qwen").trim().toLowerCase();
  if (provider === "local" || provider === "openai")
    return {
      provider,
      style: "openai",
      url:
        (process.env.CHAT_API_BASE || "http://127.0.0.1:8799/v1").replace(
          /\/$/,
          "",
        ) + "/chat/completions",
      key: process.env.CHAT_API_KEY || "",
      model: process.env.CHAT_MODEL || "qwen",
    };
  if (provider === "kimi")
    return {
      provider,
      style: "anthropic",
      url:
        (
          process.env.KIMI_CODING_BASE_URL || "https://api.kimi.com/coding"
        ).replace(/\/$/, "") + "/v1/messages",
      key: process.env.KIMI_KEY,
      model: process.env.KIMI_MODEL || "kimi-for-coding",
    };
  return {
    provider: "qwen",
    style: "anthropic",
    url:
      process.env.QWEN_URL ||
      "https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic/v1/messages",
    key: process.env.QWEN_KEY,
    model: process.env.QWEN_MODEL || "qwen3.7-max",
  };
}

async function complete(config, { system, messages, tools, signal, onText }) {
  if (!config.key && config.provider !== "local")
    throw Object.assign(new Error("模型尚未配置，请联系维护者。"), {
      code: "model_config",
    });
  const anthropic = config.style === "anthropic";
  const headers = { "content-type": "application/json" };
  if (anthropic) {
    headers["anthropic-version"] = "2023-06-01";
    headers[config.provider === "qwen" ? "x-api-key" : "authorization"] =
      config.provider === "qwen" ? config.key : "Bearer " + config.key;
  } else if (config.key) headers.authorization = "Bearer " + config.key;
  let wireMessages = messages;
  if (!anthropic)
    wireMessages = [
      { role: "system", content: system },
      ...messages.flatMap((m) => {
        if (typeof m.content === "string") return [m];
        const text = m.content
          .filter((b) => b.type === "text")
          .map((b) => b.text)
          .join("");
        const calls = m.content
          .filter((b) => b.type === "tool_use")
          .map((b) => ({
            id: b.id,
            type: "function",
            function: { name: b.name, arguments: JSON.stringify(b.input) },
          }));
        const results = m.content
          .filter((b) => b.type === "tool_result")
          .map((b) => ({
            role: "tool",
            tool_call_id: b.tool_use_id,
            content: b.content,
          }));
        return results.length
          ? results
          : [
              {
                role: m.role,
                content: text || null,
                ...(calls.length ? { tool_calls: calls } : {}),
              },
            ];
      }),
    ];
  const body = {
    model: config.model,
    max_tokens: 2200,
    messages: wireMessages,
    stream: true,
  };
  if (anthropic) body.system = system;
  if (tools?.length)
    body.tools = anthropic
      ? tools
      : tools.map((t) => ({
          type: "function",
          function: {
            name: t.name,
            description: t.description,
            parameters: t.input_schema,
          },
        }));
  if (config.provider === "local")
    body.chat_template_kwargs = { enable_thinking: false };
  const response = await fetch(config.url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    if ([401, 403].includes(response.status))
      throw Object.assign(new Error("模型凭证已失效，正在等待维护者更新。"), {
        code: "model_auth",
      });
    if (response.status === 429)
      throw Object.assign(new Error("模型当前繁忙，请稍后重试。"), {
        code: "model_busy",
      });
    throw Object.assign(new Error("模型暂时无法响应，请稍后重试。"), {
      code: "model_upstream",
    });
  }
  if (
    !String(response.headers.get("content-type")).includes("text/event-stream")
  ) {
    const d = await response.json();
    const message = d.choices?.[0]?.message;
    const blocks = anthropic
      ? d.content
      : [
          { type: "text", text: message?.content || "" },
          ...(message?.tool_calls || []).map((c) => ({
            type: "tool_use",
            id: c.id,
            name: c.function.name,
            input: JSON.parse(c.function.arguments),
          })),
        ];
    for (const b of blocks || [])
      if (b.type === "text" && b.text) onText(b.text);
    return blocks || [];
  }
  const blocks = [];
  const openaiCalls = new Map();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  function consume(event) {
    const payload = event
      .split("\n")
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).trim())
      .join("\n");
    if (!payload || payload === "[DONE]") return;
    const d = JSON.parse(payload);
    if (d.type === "error" || d.error)
      throw Object.assign(new Error("模型响应中断，请重试。"), {
        code: "model_upstream",
      });
    if (anthropic) {
      if (d.type === "content_block_start")
        blocks[d.index] = { ...d.content_block };
      if (d.type === "content_block_delta") {
        const b = blocks[d.index];
        if (!b) return;
        if (d.delta.type === "text_delta") {
          b.text = (b.text || "") + d.delta.text;
          onText(d.delta.text);
        }
        if (d.delta.type === "input_json_delta")
          b.raw = (b.raw || "") + d.delta.partial_json;
      }
    } else {
      const delta = d.choices?.[0]?.delta || {};
      if (delta.content) {
        if (!blocks[0]) blocks[0] = { type: "text", text: "" };
        blocks[0].text += delta.content;
        onText(delta.content);
      }
      for (const call of delta.tool_calls || []) {
        const c = openaiCalls.get(call.index) || {
          type: "tool_use",
          id: "",
          name: "",
          raw: "",
        };
        c.id += call.id || "";
        c.name += call.function?.name || "";
        c.raw += call.function?.arguments || "";
        openaiCalls.set(call.index, c);
      }
    }
  }
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, "\n");
    let i;
    while ((i = buffer.indexOf("\n\n")) >= 0) {
      consume(buffer.slice(0, i));
      buffer = buffer.slice(i + 2);
    }
  }
  if (buffer.trim()) consume(buffer);
  for (const c of openaiCalls.values()) blocks.push(c);
  return blocks
    .filter((b) => b && ["text", "tool_use"].includes(b.type))
    .map((b) => {
      if (b.type === "tool_use") {
        b.input = b.raw ? JSON.parse(b.raw) : b.input || {};
        delete b.raw;
      }
      return b;
    });
}
module.exports = { configuration, complete };
