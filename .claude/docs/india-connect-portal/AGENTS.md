<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Secrets

`.env` is gitignored and must never be committed. Copy `.env.example` to
`.env` locally and fill in real values there.

`VITE_LOVABLE_CONNECTOR_GOOGLE_MAPS_BROWSER_KEY` (Google Maps JS API browser
key, used by `src/components/kavach/RealWorldMap.tsx`) must always be
supplied out-of-band — via the local `.env` for dev, or the deploy
environment's secret store in CI/production — never hardcoded or committed.
Restrict it by HTTP referrer in the Google Cloud Console to the exact origins
that use it. See [spec.md](../../../India%20Connect%20Portal/spec.md) Phase 0
for the rest of this folder's security baseline.
