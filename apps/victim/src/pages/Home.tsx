import { ChevronRight, MessageSquare, Phone, ShieldCheck } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import ModePill from '../components/ModePill';

export default function Home() {
  const navigate = useNavigate();

  function onCall() {
    alert('Voice support is coming soon — please use Text for now.');
  }

  return (
    <div className="flex min-h-full flex-col bg-zinc-950">
      <header className="mx-auto w-full max-w-md px-5 pt-[env(safe-area-inset-top)]">
        <div className="flex items-center justify-between pt-4">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-zinc-400">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
            Disaster Relief
          </span>
          <ModePill />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col px-5 pt-8 pb-10">
        <h1 className="text-3xl font-bold leading-tight text-zinc-50 sm:text-4xl">
          Disaster Relief
        </h1>
        <p className="mt-3 text-lg leading-relaxed text-zinc-300">
          If you need help, press a button below. We will read or hear what you
          say and send the closest team that can help.
        </p>

        <div className="mt-8 flex flex-col gap-4">
          <button
            type="button"
            onClick={onCall}
            className="flex min-h-[80px] w-full items-center justify-center gap-3 rounded-2xl bg-rose-600 px-6 py-5 text-2xl font-semibold text-white shadow-lg shadow-rose-900/40 transition-colors hover:bg-rose-500 active:bg-rose-700"
          >
            <Phone className="h-7 w-7" aria-hidden />
            Call for help
          </button>

          <button
            type="button"
            onClick={() => navigate('/incident')}
            className="flex min-h-[80px] w-full items-center justify-center gap-3 rounded-2xl border-2 border-zinc-200 bg-zinc-900 px-6 py-5 text-2xl font-semibold text-zinc-50 transition-colors hover:bg-zinc-800 active:bg-zinc-950"
          >
            <MessageSquare className="h-7 w-7" aria-hidden />
            Text for help
          </button>
        </div>

        <section
          aria-label="Things you can mention"
          className="mt-8 rounded-2xl bg-amber-500/10 p-5 ring-1 ring-amber-500/30"
        >
          <p className="text-sm font-semibold uppercase tracking-wider text-amber-200">
            Things you can mention
          </p>
          <ul className="mt-3 space-y-2 text-base leading-relaxed text-amber-50/90">
            <li>• Where you are</li>
            <li>• What happened</li>
            <li>• Who is hurt</li>
            <li>• What you have</li>
            <li>• What you need</li>
          </ul>
        </section>

        <div className="mt-auto pt-10">
          <Link
            to="/onboard"
            className="inline-flex items-center gap-1 text-sm font-medium text-zinc-400 underline-offset-4 hover:text-zinc-200 hover:underline"
          >
            Save your info (optional)
            <ChevronRight className="h-4 w-4" aria-hidden />
          </Link>
          <Link
            to="/demo"
            className="ml-4 inline-flex items-center gap-1 text-sm font-medium text-zinc-500 underline-offset-4 hover:text-zinc-300 hover:underline"
          >
            Reviewer preview
            <ChevronRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </main>
    </div>
  );
}
