module.exports = async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const { category, company, drug, is_alert, page = 0, limit = 20 } = req.query;
  const offset = parseInt(page) * parseInt(limit);

  const SUPABASE_URL = process.env.SUPABASE_URL;
  const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;

  const cols = 'id,catchy_title,raw_title,product_name,company,indication,category,relevance_score,summary,alert_text,article_date,url,is_alert';
  let params = `select=${cols}&order=article_date.desc,relevance_score.desc&relevance_score=gte.4`;

  if (category)  params += `&category=eq.${encodeURIComponent(category)}`;
  if (company)   params += `&company=ilike.${encodeURIComponent('%' + company + '%')}`;
  if (drug)      params += `&product_name=ilike.${encodeURIComponent('%' + drug + '%')}`;
  if (is_alert === 'true')  params += `&is_alert=eq.true`;
  if (is_alert === 'false') params += `&is_alert=eq.false`;

  const url = `${SUPABASE_URL}/rest/v1/articles?${params}`;
  const r = await fetch(url, {
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      Range: `${offset}-${offset + parseInt(limit) - 1}`,
      'Range-Unit': 'items',
      Prefer: 'count=exact',
    },
  });

  if (!r.ok) {
    const errText = await r.text();
    return res.status(r.status).json({ error: 'Supabase error', status: r.status, detail: errText, url_used: url.replace(SUPABASE_KEY, '***') });
  }

  const data = await r.json();
  const contentRange = r.headers.get('content-range') || '';
  const total = parseInt((contentRange.split('/')[1] || '0'));

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.status(200).json({ articles: data, total, page: parseInt(page), limit: parseInt(limit) });
}
