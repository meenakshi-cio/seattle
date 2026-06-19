import { neon } from '@neondatabase/serverless';

const sql = neon(process.env.DATABASE_URL);

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();

  if (req.method === 'GET') {
    const rows = await sql`SELECT listing_id FROM viewed_listings`;
    return res.json(rows.map(r => r.listing_id));
  }

  if (req.method === 'POST') {
    const { id } = req.body;
    if (!id) return res.status(400).json({ error: 'missing id' });
    await sql`INSERT INTO viewed_listings (listing_id) VALUES (${id}) ON CONFLICT DO NOTHING`;
    return res.status(200).json({ ok: true });
  }

  if (req.method === 'DELETE') {
    const { id } = req.body;
    if (!id) return res.status(400).json({ error: 'missing id' });
    await sql`DELETE FROM viewed_listings WHERE listing_id = ${id}`;
    return res.status(200).json({ ok: true });
  }

  return res.status(405).json({ error: 'method not allowed' });
}
