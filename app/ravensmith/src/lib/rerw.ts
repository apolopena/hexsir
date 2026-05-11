import AnsiToHtml from "ansi-to-html";

const converter = new AnsiToHtml({
  fg: "#e5e7eb", // tailwind slate-200, dark-mode default body fg
  bg: "transparent",
  newline: false, // we do our own \n → <br> handling
  escapeXML: true, // safety: any `<`/`&` in rerw output is escaped before HTML
});

/**
 * Collapse carriage-return rewrites: display_lib's spinners write
 * `\r<frame>` to overwrite the current line in a real terminal.
 * ansi-to-html does NOT model `\r` as cursor-to-column-0 — without this
 * pre-pass, every spinner tick lands in the output as accumulated text
 * and the user sees hundreds of frames stacked. Per line, keep only the
 * segment after the final `\r` (= what would be visible after the last
 * rewrite finished).
 */
export function collapseCR(raw: string): string {
  return raw
    .split("\n")
    .map((line) => {
      const idx = line.lastIndexOf("\r");
      return idx === -1 ? line : line.slice(idx + 1);
    })
    .join("\n");
}

/**
 * Render a buffer of ANSI-decorated rerw output to HTML safe for v-html
 * binding. `escapeXML: true` on the converter is the XSS gate — rerw
 * output may contain user data (savefile paths, hero names) that could
 * include `<` or `&`; these get HTML-escaped before any span tags are
 * applied.
 */
export function renderRerwOutput(raw: string): string {
  return converter.toHtml(collapseCR(raw)).replace(/\n/g, "<br>");
}
