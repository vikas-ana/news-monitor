module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { article_id, value } = req.body;
  if (!article_id) return res.status(400).json({ error: 'article_id required' });
  if (!['thumbs_up', 'thumbs_down'].includes(value)) {
    return res.status(400).json({ error: 'value must be thumbs_up or thumbs_down' });
  }

  const SUPABASE_URL = process.env.SUPABASE_URL;
  const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;

  const r = await fetch(`${SUPABASE_URL}/rest/v1/feedback`, {
    method: 'POST',
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      'Content-Type': 'application/json',
      Prefer: 'return=minimal',
    },
    body: JSON.stringify({ article_id, value }),
  });

  if (!r.ok) return res.status(r.status).json({ error: 'Failed to save feedback' });
  res.status(200).json({ success: true });
}
