export default {
  async scheduled(event, env, ctx) {
    const resp = await fetch(
      "https://api.github.com/repos/zhangtth/hax-tg2bark/actions/workflows/monitor.yml/dispatches",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GH_PAT}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "hax-dispatch-worker",
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main" }),
      },
    );
    if (resp.status !== 204) {
      console.log("dispatch failed:", resp.status, await resp.text());
    }
  },
};
