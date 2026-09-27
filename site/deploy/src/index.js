// 단번 랜딩 Worker: 정적 자산은 그대로 두고, /media/ 영상에만 바이트 범위(Range) 응답을 붙인다.
// Cloudflare 정적 자산은 Range 에도 200 전체를 돌려주는데, iOS Safari 는 영상에 206 부분 응답을 요구한다.
export default {
  async fetch(request, env) {
    const res = await env.ASSETS.fetch(request);
    const range = request.headers.get("Range");
    if (res.status !== 200 || !new URL(request.url).pathname.startsWith("/media/")) return res;
    const headers = new Headers(res.headers);
    headers.set("Accept-Ranges", "bytes");
    if (!range) return new Response(res.body, { status: 200, headers });

    const buf = await res.arrayBuffer();
    const size = buf.byteLength;
    const m = /^bytes=(\d*)-(\d*)$/.exec(range.trim());   // 한 구간만(브라우저 영상 요청은 한 구간)
    let start, end;
    if (m && m[1] !== "") { start = +m[1]; end = m[2] !== "" ? Math.min(+m[2], size - 1) : size - 1; }
    else if (m && m[2] !== "") { start = Math.max(size - +m[2], 0); end = size - 1; }   // 끝에서 N바이트
    if (start === undefined || start > end || start >= size) {
      headers.set("Content-Range", `bytes */${size}`);
      headers.delete("Content-Length");
      return new Response(null, { status: 416, headers });
    }
    headers.set("Content-Range", `bytes ${start}-${end}/${size}`);
    headers.set("Content-Length", String(end - start + 1));
    return new Response(request.method === "HEAD" ? null : buf.slice(start, end + 1), { status: 206, headers });
  },
};
