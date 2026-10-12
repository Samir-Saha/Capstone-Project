import Link from "next/link";

export default function NotFound() {
  return (
    <div className="panel mx-auto max-w-lg p-8 text-center">
      <h1 className="h-display text-3xl">Nothing here</h1>
      <p className="mt-2 text-muted">That page doesn't exist, or the session was cleared.</p>
      <Link href="/" className="btn-primary mt-6">
        Back to the hub
      </Link>
    </div>
  );
}
