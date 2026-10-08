/** spec §7.2: 浏览器 UTF-16 offset → Unicode 码点 offset 转换与字素边界验证。 */

// Intl.Segmenter 类型声明（TS lib 可能未包含）
declare global {
  namespace Intl {
    class Segmenter {
      constructor(locales?: string | string[], options?: { granularity?: string });
      segment(text: string): Iterable<{ segment: string; index: number }>;
    }
  }
}

/** 检查 UTF-16 offset 是否落在代理对中间；是则抛错。 */
export function assertNotInsideSurrogatePair(text: string, utf16Offset: number): void {
  if (utf16Offset <= 0 || utf16Offset >= text.length) return;
  const prev = text.charCodeAt(utf16Offset - 1);
  const curr = text.charCodeAt(utf16Offset);
  const isLead = prev >= 0xd800 && prev <= 0xdbff;
  const isTrail = curr >= 0xdc00 && curr <= 0xdfff;
  if (isLead && isTrail) {
    throw new Error("split_offset_inside_surrogate_pair: 切分点落在代理对中间");
  }
}

/** UTF-16 offset → 码点 offset（先验证不在代理对中间）。 */
export function utf16ToCodePoint(text: string, utf16Offset: number): number {
  assertNotInsideSurrogatePair(text, utf16Offset);
  return Array.from(text.slice(0, utf16Offset)).length;
}

/** 用 Intl.Segmenter 验证码点 offset 是否落在扩展字素簇边界。 */
export function isGraphemeBoundary(text: string, codePointOffset: number): boolean {
  const cps = Array.from(text);
  if (codePointOffset < 0 || codePointOffset > cps.length) return false;
  if (codePointOffset === 0 || codePointOffset === cps.length) return true;
  const seg = new Intl.Segmenter(undefined, { granularity: "grapheme" });
  let cp = 0;
  for (const { segment } of seg.segment(text)) {
    if (cp === codePointOffset) return true;
    if (cp > codePointOffset) return false;
    cp += Array.from(segment).length;
  }
  return cp === codePointOffset;
}

/** 选区（UTF-16 offsets）→ 码点 offsets，含全部校验。 */
export function selectionToCodePoints(
  text: string,
  utf16Start: number,
  utf16End: number,
): number[] {
  const cpLen = Array.from(text).length;
  const cps = [utf16ToCodePoint(text, utf16Start), utf16ToCodePoint(text, utf16End)].sort(
    (a, b) => a - b,
  );
  // 切分点必须在 1..len-1 且落在字素簇边界
  const bad = cps.filter((o) => o <= 0 || o >= cpLen || !isGraphemeBoundary(text, o));
  if (bad.length > 0) {
    throw new Error(
      `split_offset_not_grapheme_boundary: 切分点 ${bad.join(",")} 非法（须在 1..${cpLen - 1} 且落在字素簇边界，组合符号/ZWJ emoji 不可切）`,
    );
  }
  return [...new Set(cps)];
}
