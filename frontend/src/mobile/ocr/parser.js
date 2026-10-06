/**
 * 证件字段抽取：OCR 文字行（含框坐标）→ 结构化字段。
 *
 * 原则：
 * - **版式规则 + 框坐标**，不做像素模板（模板对倾斜/远近敏感，脆）：
 *   身份证版式国标固定——姓名在「姓名」标签行的右侧或正下方；
 *   住址在「住址」标签以下、号码行以上的区域（可跨两行）；号码是最底部 18 位。
 * - ⛔ OCR 返回顺序不保证是阅读顺序（第二行住址可能排在号码行之后），
 *   所以先按框坐标排好阅读顺序，再做行序遍历。
 * - ⛔ 标签词黑名单：OCR 把「姓名」标签误读成「名字」时，绝不能把标签行当值
 *   （事故：姓名字段返回"名字"）。
 * - 每个字段携带 score（命中行置信度均值），供确认表单做低置信度提示。
 * - 身份证号校验复用 `utils/validators.js::diagnoseChinaId`（与保存闸门同口径）。
 */

import { diagnoseChinaId } from "../../utils/validators.js";

/** 单行分值上限，防个别行拖垮字段置信度 */
const SCORE_CAP = 0.95;

/** 这些词是「标签被 OCR 误读」的产物，永远不能当字段值 */
const LABEL_WORD = /^(名字|姓名|性别|民族|出生|住址|公民身份号码|签发机关|有效期限|汉|男|女|长期)$/;

/**
 * 判断 OCR 文字行更像身份证哪一面。
 * @returns {"id_front"|"id_back"|null}
 */
export function detectDocType(lines) {
  const text = joinText(lines);
  if (/公民身份号码/.test(text)) return "id_front";
  if (/签发机关/.test(text) && /有效期限/.test(text)) return "id_back";
  // 光照/反光导致标签字没认全时的兜底：18 位号码在 → 人像面
  if (findIdNo(text)) return "id_front";
  if (/\d{4}[.．/年]\d{1,2}[.．/月]\d{1,2}\s*[-—~至]+\s*(\d{4}[.．/年]|长期)/.test(text)) {
    return "id_back";
  }
  return null;
}

/**
 * 解析身份证人像面。
 * @returns {{ fields: Array<{key,label,value,score,warning}>, idNoValid: boolean }}
 */
export function parseIdCardFront(lines) {
  const ordered = readingOrder(lines);
  const text = joinText(ordered);
  const idNo = findIdNo(text);
  const idNoIssue = idNo ? diagnoseChinaId(idNo) : null;
  // diagnoseChinaId 返回 {code, message}：code 为空串 = 通过（与保存闸门同口径）
  const idNoValid = Boolean(idNo) && !idNoIssue?.code;

  const name = extractName(ordered);
  const address = extractAddress(ordered);

  const fields = [    {
      key: "name",
      label: "姓名",
      value: name,
      score: fieldScore(ordered, /姓名|名字/),
      warning: name
        ? ""
        : "未识别到姓名，请人工填写",
    },
    {
      key: "idNo",
      label: "身份证号",
      value: idNo || "",
      score: idNo ? fieldScore(ordered, /公民身份号码|\d{17}[\dXx]/) : 0,
      warning: idNo
        ? idNoValid
          ? ""
          : `校验不通过${idNoIssue?.message ? `：${idNoIssue.message}` : ""}`
        : "未识别到 18 位号码",
    },
    {
      key: "address",
      label: "住址",
      value: address,
      score: fieldScore(ordered, /住址/),
      warning: address
        ? address.length < 6
          ? "住址可能不完整，请核对补全"
          : ""
        : "未识别到住址，请人工填写",
    },
  ];
  return { fields, idNoValid, geometryOk: checkFrontGeometry(lines, idNo) };
}

/**
 * 人像面几何合理性：18 位号码所在行必须是全图最底部（cy 最大）的行。
 * 识别引擎逐行纠正了文字方向，倒立的图**内容全对但行序颠倒**——
 * 用这条判据识别"转错方向"的识别结果（地址串进姓名等错位都源于此）。
 * 无坐标信息时视为合理（不拦截）。
 */
function checkFrontGeometry(lines, idNo) {
  if (!idNo) return true;
  let idNoCy = null;
  let maxCy = null;
  for (const line of lines) {
    const box = boxOf(line);
    if (!box) continue;
    if (maxCy === null || box.cy > maxCy) maxCy = box.cy;
    if (normalize(line.text).includes(idNo)) idNoCy = box.cy;
  }
  if (idNoCy === null || maxCy === null) return true;
  return idNoCy >= maxCy - 1e-6 || idNoCy >= maxCy - 0.25 * Math.abs(maxCy) - 20;
}

/**
 * 解析身份证国徽面。
 * @returns {{ fields: Array<{key,label,value,score,warning}>, idNoValid: boolean, geometryOk: boolean }}
 */
export function parseIdCardBack(lines) {
  const ordered = readingOrder(lines);
  const text = joinText(ordered);
  const validMatch = text.match(
    /(\d{4}[.．/年]\d{1,2}[.．/月]\d{1,2})\s*[-—~至]+\s*(\d{4}[.．/年]\d{1,2}[.．/月]\d{1,2}|长期)/,
  );
  const authority = extractAfter(ordered, /签发机关/);
  const validPeriod = validMatch ? `${validMatch[1]}-${validMatch[2]}` : "";

  const fields = [
    {
      key: "authority",
      label: "签发机关",
      value: authority,
      score: fieldScore(ordered, /签发机关/),
      warning: authority ? "" : "未识别到签发机关，请人工填写",
    },
    {
      key: "validPeriod",
      label: "有效期限",
      value: validPeriod,
      score: validPeriod ? fieldScore(ordered, /有效期限/) : 0,
      warning: validPeriod ? "" : "未识别到有效期限",
    },
  ];
  return { fields, idNoValid: true, geometryOk: checkBackGeometry(lines) };
}

/** 国徽面几何合理性：签发机关行应在有效期限行上方（同倒立判据） */
function checkBackGeometry(lines) {
  let authorityCy = null;
  let periodCy = null;
  for (const line of lines) {
    const box = boxOf(line);
    if (!box) continue;
    const text = normalize(line.text);
    if (authorityCy === null && /签发机关/.test(text)) authorityCy = box.cy;
    if (periodCy === null && /有效期限/.test(text)) periodCy = box.cy;
  }
  if (authorityCy === null || periodCy === null) return true;
  return authorityCy < periodCy;
}

/* ------------------------------------------------------------------ */
/* 户口簿（首页 / 常住人口登记卡个人页）                                   */
/* ------------------------------------------------------------------ */

/** 户口簿页强特征词：身份证上绝不会出现这些词（"户主"含登记卡行值） */
const HOUSEHOLD_PATTERN = /户口簿|常住人口登记卡|户主或与户主关系|户别|户号|户主/;

/**
 * 判断 OCR 文字行是否是户口簿页。
 * ⛔ 必须在 detectDocType 之前调用：登记卡里出现 18 位号码会被
 * detectDocType 的"号码兜底"误判成身份证人像面。
 */
export function detectHouseholdRegister(lines) {
  return HOUSEHOLD_PATTERN.test(joinText(lines));
}

/**
 * 解析户口簿个人页（常住人口登记卡）。
 * 各省版式不一、无固定几何，不做 geometryOk 检查（恒 true）；
 * 方向重试改用"姓名认出来了"这一内容判据（见 idCapture.js）。
 * 字段：姓名 / 性别（返回"男|女"原文）/ 与户主关系（返回登记原文，由调用方
 * 对字典做模糊匹配）/ 证件号码（未成年人可能未编号，允许为空）。
 * 同时返回 rawText（识别原文前 400 字）——登记卡满页小字、标签常被误读，
 * 字段抽不齐时用户截图原文即可回传定位（真机调参的数据通道）。
 */
export function parseHouseholdRegister(lines) {
  const ordered = readingOrder(lines);
  const text = joinText(ordered);
  const idNo = findIdNo(text);

  const name = extractHouseholdName(ordered);
  const genderText = extractByLabel(ordered, /性别/, /^(男|女|男性|女性)$/);
  // 关系值必须含亲属称谓字（子/女/父/母/孙/户主/本人…）——邻域扫描会把
  // 别的栏目的纯汉字值（如姓名行）误抓成关系，称谓字是最后一道闸门
  const relation = extractByLabel(
    ordered,
    /户主或与户主关系|与户主关系/,
    /^(?=.*[子女媳婿父母孙兄弟姐妹叔伯舅姑姨侄甥户本其])[\u4e00-\u9fa5·]{1,8}$/,
  );

  const fields = [
    {
      key: "name",
      label: "姓名",
      value: name,
      score: fieldScore(ordered, /姓名|名字/),
      warning: name ? "" : "未识别到姓名，请人工填写",
    },
    {
      key: "gender",
      label: "性别",
      value: genderText ? genderText.replace(/性$/, "") : "",
      score: genderText ? fieldScore(ordered, /性别/) : 0,
      warning: genderText ? "" : "未识别到性别，请人工选择",
    },
    {
      key: "relationToHead",
      label: "与户主关系",
      value: relation,
      score: relation ? fieldScore(ordered, /户主|关系/) : 0,
      warning: relation ? "" : "未识别到与户主关系，请人工选择",
    },
    {
      key: "idNo",
      label: "证件号码",
      value: idNo || "",
      score: idNo ? fieldScore(ordered, /\d{17}[\dXx]/) : 0,
      warning: idNo ? "" : "本页未识别到 18 位证件号码（未成年人可能尚未编号），请人工填写",
    },
  ];
  return { fields, idNoValid: true, geometryOk: true, rawText: text.slice(0, 400) };
}

/**
 * 登记卡字段值切分：OCR 常把同一排的多组「标签 值」合并成一行，
 * 值的尾部会粘上下一个标签（如「之子性别男」）——在已知标签词处截断。
 * 标签词字典来自常住人口登记卡版式；真名含这些字的情况（如姓名带"村"）
 * 由调用方的 valuePattern 再筛，风险可控。
 */
const HOUSEHOLD_NEXT_LABEL =
  /户主或与户主关系|与户主关系|公民身份证件编号|身份证件编号|身份证编号|兵役状况|服务处所|宗教信仰|婚姻状况|文化程度|曾用名|常住人口|登记卡|户口簿|签发日期|签发人|承办人|户别|户号|户主|姓名|性别|民族|出生|籍贯|住址|职业|血型/;

function cutAtNextLabel(value) {
  // 从 index>0 找最早标签词出现处截断；index 0 处的标签词可能是值本身
  // （如关系值就是"户主"），保留并从其后继续找下一个标签
  const re = new RegExp(HOUSEHOLD_NEXT_LABEL.source, "g");
  let match;
  while ((match = re.exec(value))) {
    if (match.index > 0) return value.slice(0, match.index);
    re.lastIndex = match.index + match[0].length;
  }
  return value;
}

/** 登记卡姓名值黑名单：标题/栏目词能通过通用姓名校验，须显式排除 */
const HOUSEHOLD_NAME_BAN = /兵役|服务处所|宗教|籍贯|户别|户号|登记|签发|承办|社区|村委会|住址|民族|出生/;

/** 邻域扫描的姓名额外闸门：民族（汉族）、户别（农业家庭户）、性别（男/女）这类高频词 */
function isHouseholdNameValue(value) {
  return (
    isValidName(value) &&
    !HOUSEHOLD_NAME_BAN.test(value) &&
    !/^(男|女)$/.test(value) &&
    !/族$/.test(value) &&
    !/户口$|(家庭|集体)户?$/.test(value)
  );
}

/**
 * 登记卡姓名提取。
 * ⛔ 与身份证不同：**没有盲抓兜底**——登记卡满页都是「未服兵役」「服务处所」
 * 这类能通过通用姓名校验的纯汉字短行（真机事故：姓名抓成"未服役"），
 * 值必须能锚定到「姓名」标签（行内联或标签行邻域）才算数。
 */
function extractHouseholdName(lines) {
  // 1) 行内联：「姓名张三」或整排合并「姓名张三户主或与户主关系之子…」
  for (const line of lines) {
    const text = normalize(line.text);
    const inline = text.match(/姓名[::]?(.+)/);
    if (inline && inline[1]) {
      const value = cutAtNextLabel(cleanName(inline[1]));
      if (isHouseholdNameValue(value)) return value;
    }
  }

  // 2) 「姓名」标签独立成行：取右侧同行或正下方的行
  const labelIndex = lines.findIndex((line) => /^(户主)?姓名[::]?$/.test(normalize(line.text)));
  if (labelIndex >= 0) {
    const label = boxOf(lines[labelIndex]);
    if (label) {
      const rightCandidates = [];
      const belowCandidates = [];
      lines.forEach((line, index) => {
        if (index === labelIndex) return;
        const box = boxOf(line);
        if (!box) return;
        if (Math.abs(box.cy - label.cy) < 0.9 * Math.max(box.h, label.h) && box.x0 >= label.x1 - label.h * 0.5) {
          rightCandidates.push({ line, box });
        } else if (box.y0 > label.y1) {
          belowCandidates.push({ line, box });
        }
      });
      rightCandidates.sort((a, b) => a.box.x0 - b.box.x0);
      for (const { line } of rightCandidates) {
        const value = cutAtNextLabel(cleanName(normalize(line.text)));
        if (isHouseholdNameValue(value)) return value;
      }
      // 正下方按 y 近到远扫（登记卡两列版式 x 对不齐，靠 valuePattern 把关）
      belowCandidates.sort((a, b) => a.box.y0 - b.box.y0);
      for (const { line } of belowCandidates) {
        const value = cutAtNextLabel(cleanName(normalize(line.text)));
        if (isHouseholdNameValue(value)) return value;
      }
    }
  }
  return "";
}

/**
 * 登记卡取值：标签行右侧同行的最近值，其次正下方最近值。
 * 登记卡是"标签列 + 值列"版式，OCR 可能把一行并排的多组"标签 值"合成一行，
 * 所以行内联取值要依次尝试整段 / 前 2 字 / 前 1 字能否通过 valuePattern。
 */
function extractByLabel(lines, labelPattern, valuePattern) {
  for (const line of lines) {
    const text = normalize(line.text);
    const inline = text.match(new RegExp(`(?:${labelPattern.source})[::]?(.*)`));
    if (inline && inline[1]) {
      // 整排合并行：值尾部粘着下一个标签（"之子性别男"），先切再验
      const inlineValue = cutAtNextLabel(inline[1]);
      const rawValue = inline[1];
      for (const candidate of [inlineValue, rawValue, rawValue.slice(0, 2), rawValue.slice(0, 1)]) {
        if (candidate && valuePattern.test(candidate)) return candidate.slice(0, 12);
      }
    }
  }

  const labelIndex = lines.findIndex((line) =>
    new RegExp(`^(?:${labelPattern.source})[::]?$`).test(normalize(line.text)),
  );
  if (labelIndex < 0) return "";
  const label = boxOf(lines[labelIndex]);
  if (!label) return "";

  const rightCandidates = [];
  const belowCandidates = [];
  lines.forEach((line, index) => {
    if (index === labelIndex) return;
    const box = boxOf(line);
    if (!box) return;
    if (Math.abs(box.cy - label.cy) < 0.9 * Math.max(box.h, label.h) && box.x0 >= label.x1 - label.h * 0.5) {
      rightCandidates.push({ line, box });
    } else if (box.y0 > label.y1) {
      belowCandidates.push({ line, box });
    }
  });
  rightCandidates.sort((a, b) => a.box.x0 - b.box.x0);
  for (const { line } of rightCandidates) {
    const value = cutAtNextLabel(normalize(line.text));
    if (valuePattern.test(value)) return value.slice(0, 12);
  }
  // 登记卡两列版式标签列与值列 x 对不齐，正下方候选不按 cx 过滤、
  // 按 y 由近到远扫，valuePattern 是唯一的正确性闸门
  belowCandidates.sort((a, b) => a.box.y0 - b.box.y0);
  for (const { line } of belowCandidates) {
    const value = cutAtNextLabel(normalize(line.text));
    if (valuePattern.test(value)) return value.slice(0, 12);
  }
  return "";
}

/* ------------------------------------------------------------------ */
/* 坐标工具                                                             */
/* ------------------------------------------------------------------ */

/**
 * 按阅读顺序重排行：y 中心为主序；同一行（y 中心接近）按 x 升序。
 * 识别引擎的返回顺序≈检出顺序，不保证从上到下——不排这步，
 * 「第二行住址排在号码行后面」就会把地址截断。
 */
function readingOrder(lines) {
  const decorated = lines.map((line) => {
    const box = boxOf(line);
    return { line, ...box };
  });
  decorated.sort((a, b) => a.cy - b.cy || a.x0 - b.x0);
  // 同行相邻对修正（合并行 y 中心不完全一致的情形）
  for (let i = 0; i < decorated.length - 1; i += 1) {
    const a = decorated[i];
    const b = decorated[i + 1];
    if (Math.abs(a.cy - b.cy) < 0.7 * Math.max(a.h, b.h, 1) && a.x0 > b.x0) {
      decorated[i] = b;
      decorated[i + 1] = a;
    }
  }
  return decorated.map((d) => d.line);
}

/** 行的外接框：{x0,y0,x1,y1,cx,cy,h}，无坐标时返回 null */
function boxOf(line) {
  const points = Array.isArray(line?.box) ? line.box : [];
  if (!points.length) return null;
  const xs = points.map((p) => Number(p.x) || 0);
  const ys = points.map((p) => Number(p.y) || 0);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);
  return { x0, x1, y0, y1, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, h: Math.max(y1 - y0, 1) };
}

/* ------------------------------------------------------------------ */
/* 字段抽取                                                             */
/* ------------------------------------------------------------------ */

function joinText(lines) {
  return lines
    .map((line) => normalize(line.text))
    .filter(Boolean)
    .join("\n");
}

/** 全角转半角、去空白，OCR 输出常见全角标点/空格混排 */
function normalize(text) {
  return String(text || "")
    .replace(/[\uFF01-\uFF5E]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xfee0))
    .replace(/\s+/g, "");
}

function findIdNo(text) {
  const match = normalize(text).match(/(?<!\d)(\d{17}[\dXx])(?!\d)/);
  return match ? match[1].toUpperCase() : "";
}

/** 姓名值合法性：纯汉字（少数民族可带 ·），且不是标签词 */
function isValidName(value) {
  return (
    Boolean(value) &&
    /^[\u4e00-\u9fa5·]{2,15}$/.test(value) &&
    !LABEL_WORD.test(value) &&
    !/性别|民族|出生|住址|号码/.test(value)
  );
}

function extractName(lines) {
  // 1) 同行内联：「姓名张三」（最常见的检出形态）
  for (const line of lines) {
    const text = normalize(line.text);
    const inline = text.match(/姓名[::]?(.+)/);
    if (inline && inline[1] && !/性别|民族|出生|住址/.test(inline[1])) {
      const value = cleanName(inline[1]);
      if (isValidName(value)) return value;
    }
  }

  // 2) 标签行独立：「姓名」/被误读的「名字」是标签锚点，取它右侧（同行）或正下方的行
  const labelIndex = lines.findIndex((line) => /^(姓名|名字)[::]?$/.test(normalize(line.text)));
  if (labelIndex >= 0) {
    const label = boxOf(lines[labelIndex]);
    if (label) {
      // 右侧同行：y 中心接近、x 在标签右侧，取最靠左的那个
      const rightCandidates = [];
      lines.forEach((line, index) => {
        if (index === labelIndex) return;
        const box = boxOf(line);
        if (!box) return;
        if (Math.abs(box.cy - label.cy) < 0.8 * Math.max(box.h, label.h) && box.x0 >= label.x1 - label.h * 0.5) {
          rightCandidates.push({ line, box });
        }
      });
      rightCandidates.sort((a, b) => a.box.x0 - b.box.x0);
      for (const { line } of rightCandidates) {
        const value = cleanName(normalize(line.text));
        if (isValidName(value)) return value;
      }
      // 正下方：x 大致对齐标签列、y 在标签下方，取最近的一行
      const belowCandidates = [];
      lines.forEach((line, index) => {
        if (index === labelIndex) return;
        const box = boxOf(line);
        if (!box) return;
        if (box.y0 > label.y1 && Math.abs(box.cx - label.cx) < Math.max(label.h * 3, box.h * 2)) {
          belowCandidates.push({ line, box });
        }
      });
      belowCandidates.sort((a, b) => a.box.y0 - b.box.y0);
      for (const { line } of belowCandidates) {
        const value = cleanName(normalize(line.text));
        if (isValidName(value)) return value;
      }
    }
  }

  // 3) 兜底：最顶上的合法姓名行（排除标签词——"名字"就是在这里混进来的）
  for (const line of lines.slice(0, 4)) {
    const value = cleanName(normalize(line.text));
    if (isValidName(value)) return value;
  }
  return "";
}

function cleanName(text) {
  // ⛔ 只清洗标点，不能删「姓/名」字本身（真名可能含"名"字）
  return text.replace(/[[\]:：\s]/g, "").slice(0, 30);
}

/**
 * 住址：「住址」标签以下、号码行以上的区域整体收集（可跨两行）。
 * 号码行判据：含「公民身份」或 18 位号码（标签没认出、号码认出的情形）。
 */
function extractAddress(lines) {
  const normalized = lines.map((line) => ({ ...line, norm: normalize(line.text) }));

  // 从「住址」标签行开始收集；标签没认出来就找不到锚点，返回空
  let collecting = false;
  const parts = [];
  for (const line of normalized) {
    if (!collecting) {
      if (/住址/.test(line.norm)) {
        collecting = true;
        const inline = line.norm.replace(/.*住址[::]?/, "");
        if (inline) parts.push(inline);
      }
      continue;
    }
    // 号码行 = 收集终点（无论标签在不在）
    if (/公民身份/.test(line.norm) || /\d{17}[\dXx]/.test(line.norm)) break;
    // 标签行不该出现在住址区域；出现说明行序异常，跳过（别把姓名串进地址）
    if (/^(姓名|名字|性别|民族|出生)/.test(line.norm)) continue;
    if (line.norm) parts.push(line.norm);
  }
  return parts.join("").replace(/[[\]:：]/g, "").slice(0, 100);
}

function extractAfter(lines, labelPattern) {
  for (let i = 0; i < lines.length; i += 1) {
    const text = normalize(lines[i].text);
    if (labelPattern.test(text)) {
      const inline = text.replace(new RegExp(`.*${labelPattern.source}[::]?`), "");
      if (inline) return inline.slice(0, 60);
      if (i + 1 < lines.length) return normalize(lines[i + 1].text).slice(0, 60);
    }
  }
  return "";
}

/** 命中模式的行置信度均值（取最好的 2 行，cap 到 0.95） */
function fieldScore(lines, pattern) {
  const scores = lines
    .filter((line) => pattern.test(normalize(line.text)))
    .map((line) => Number(line.score || 0))
    .sort((a, b) => b - a)
    .slice(0, 2);
  if (!scores.length) return 0;
  const avg = scores.reduce((sum, value) => sum + value, 0) / scores.length;
  return Math.min(Math.round(avg * 100) / 100, SCORE_CAP);
}
