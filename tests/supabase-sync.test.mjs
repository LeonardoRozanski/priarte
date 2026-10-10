import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

// PostgreSQL descartável em memória. Nenhuma conexão com o projeto real.
export async function runTests() {
  const database = new PGlite();
  try {
    const setup = await readFile(new URL('../supabase-sync.sql', import.meta.url), 'utf8');
    const tests = (await readFile(new URL('./supabase-sync.test.sql', import.meta.url), 'utf8'))
      .replace(/^\\set.*$/gm, '').replace(/^\\i \/tmp\/supabase-sync\.sql.*$/gm, () => setup);
    const results = await database.exec(tests);
    return results.filter(r => r.rows?.[0]?.resultado).map(r => r.rows[0].resultado);
  } finally {
    await database.close();
  }
}
