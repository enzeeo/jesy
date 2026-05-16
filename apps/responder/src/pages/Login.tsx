import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin');
  const [error, setError] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (username === 'admin' && password === 'admin') {
      localStorage.setItem('responder-auth', '1');
      navigate('/demo');
    } else {
      setError('Invalid credentials. Use admin / admin for the demo.');
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-lg border border-zinc-800 bg-zinc-900/80 p-6 shadow-2xl backdrop-blur"
      >
        <div className="mb-5 flex items-center gap-2 text-zinc-200">
          <div className="flex h-9 w-9 items-center justify-center rounded bg-red-500/15 text-red-400 ring-1 ring-red-500/30">
            <AlertTriangle className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Responder Console</h1>
            <p className="text-[11px] uppercase tracking-widest text-zinc-500">
              Disaster Relief Command Center
            </p>
          </div>
        </div>
        <div className="space-y-3 text-sm">
          <label className="block">
            <span className="text-[11px] uppercase tracking-widest text-zinc-500">
              Username
            </span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
              autoComplete="username"
            />
          </label>
          <label className="block">
            <span className="text-[11px] uppercase tracking-widest text-zinc-500">
              Password
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
              autoComplete="current-password"
            />
          </label>
          {error ? (
            <p className="rounded bg-red-500/15 px-2 py-1 text-xs text-red-300">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            className="w-full rounded bg-emerald-500 px-3 py-2 text-sm font-semibold text-emerald-950 transition hover:bg-emerald-400"
          >
            Sign in
          </button>
          <p className="text-center text-[11px] text-zinc-500">
            Demo only — credentials are <code>admin</code> / <code>admin</code>.
          </p>
        </div>
      </form>
    </main>
  );
}
