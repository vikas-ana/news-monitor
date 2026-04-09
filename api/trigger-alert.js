export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { article_id, title } = req.body;
  if (!article_id) return res.status(400).json({ error: 'article_id required' });

  const GH_TOKEN = process.env.GH_TOKEN;
  const r = await fetch(
    'https://api.github.com/repos/vikas-ana/news-monitor/actions/workflows/fetch-news.yml/dispatches',
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${GH_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: { article_id: String(article_id) },
      }),
    }
  );

  if (r.status === 204) {
    return res.status(200).json({ success: true, message: `Alert requested for article ${article_id}` });
  }
  const err = await r.text();
  return res.status(r.status).json({ error: `GitHub API error: ${err}` });
}
