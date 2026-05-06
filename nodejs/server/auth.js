import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { one } from './db.js';

function jwtSecret() {
  return process.env.JWT_SECRET || 'development-secret-change-before-production';
}

export function signToken(user) {
  return jwt.sign(
    { sub: user.id, email: user.email, role: user.role, name: user.name },
    jwtSecret(),
    { expiresIn: '12h' }
  );
}

export async function verifyLogin(email, password) {
  const user = await one(
    'select id, email, password_hash, role, name, active from users where email = ?',
    [email]
  );
  if (!user || !user.active) return null;
  const ok = await bcrypt.compare(password, user.password_hash);
  if (!ok) return null;
  return { id: user.id, email: user.email, role: user.role, name: user.name };
}

export function requireAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: 'No autenticado' });
  try {
    req.user = jwt.verify(token, jwtSecret());
    return next();
  } catch {
    return res.status(401).json({ error: 'Sesion vencida' });
  }
}

export function requireAdmin(req, res, next) {
  if (req.user?.role !== 'admin') {
    return res.status(403).json({ error: 'Permiso insuficiente' });
  }
  return next();
}
