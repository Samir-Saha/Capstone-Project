// Typed client for the Reps API. All calls go through Next's /api rewrite.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "Can't reach the Reps API. Is the backend window running?");
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = "Some of those inputs aren't valid.";
    } catch {
      /* non-JSON error */
    }
    if (res.status === 500 && message.startsWith("Request failed")) message = "Can't reach the Reps API. Is the backend window running?";
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body ?? {}) });

const upload = <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form });

// ---------------------------------------------------------------- types

export type Health = {
  ok: boolean;
  mode: string;
  integrations: { code_runner: string; code_runner_is_sandbox: boolean; llm: string | null; supabase: boolean };
};

export type WeakTopic = { id: string; name: string; course: string; course_id: string; mastery: number; attempts: number; provisional: boolean };

export type Player = {
  name: string;
  level: number;
  xp: number;
  xp_into_level: number;
  xp_for_next: number;
  streak: number;
  best_streak: number;
  practiced_today: boolean;
  stats: { bosses_defeated: number; fights: number; questions_answered: number; problems_solved: number; interviews: number };
  weak_topics: WeakTopic[];
  continue: {
    exam: { id: string; boss_name: string; hp_current: number; course: string } | null;
    coding: { slug: string; last: string } | null;
    interview: { id: string; role: string; started_at: string } | null;
  };
  recent_xp: { reason: string; amount: number; created_at: string }[];
  xp_rules: string;
};

export type Topic = {
  id: string;
  name: string;
  description: string | null;
  mastery: number;
  attempts: number;
  correct: number;
  provisional: boolean;
};

export type Course = {
  id: string;
  name: string;
  code: string | null;
  kind: "builtin" | "uploaded";
  boss_name: string;
  hp: number;
  topics: Topic[];
  question_types: number;
  active_session_id: string | null;
  victories: number;
  fights: number;
};

export type Question = {
  id: string;
  topic_id: string;
  topic: string;
  difficulty: number;
  prompt: string;
  latex: string | null;
  answer_format: string;
  hint: string | null;
  hint_used: boolean;
  verification: { status: string; checks: string[] };
};

export type Fight = {
  id: string;
  course_id: string;
  course_name: string;
  course_code: string | null;
  boss_name: string;
  status: "active" | "completed" | "abandoned";
  outcome: "victory" | "knocked_out" | "out_of_questions" | "retreated" | null;
  hp: number;
  hp_start: number;
  victory_hp: number;
  hearts: number;
  max_hearts: number;
  combo: number;
  best_combo: number;
  question_target: number;
  asked: number;
  answered: number;
  correct: number;
  topics: Topic[];
  current_question: Question | null;
};

export type AnswerFeedback =
  | { status: "unparseable"; message: string }
  | {
      status: "graded";
      replay: boolean;
      correct: boolean;
      grading: { category: string; method: string };
      your_answer: string;
      answer: string;
      answer_latex: string | null;
      method: string | null;
      damage: number;
      mastery_before: number;
      mastery_after: number;
      xp: number;
      session: Fight;
    };

export type FightResults = {
  session: Fight;
  topics: (Topic & { asked: number; right: number; mastery_start: number })[];
  attempts: {
    topic: string;
    prompt: string;
    latex: string | null;
    answer_latex: string | null;
    method: string | null;
    difficulty: number;
    hint_used: boolean;
    answer: string;
    correct: boolean;
    grading_method: string;
    p_before: number;
    p_after: number;
    xp: number;
  }[];
  xp_earned: number;
  grading: { verified: number; ai_evaluated: number };
  next_steps: string[];
};

export type UploadResult = {
  preview: { filename: string; page_count: number; char_count: number; chunks: number; sample: { pages: number[]; text: string }[] };
  ai_available: boolean;
  job: Job | null;
  message: string;
};

export type Job = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: { stage?: string; message?: string; kept?: number; rejected?: number };
  result: { course_id: string | null; kept: number; rejected: number; message: string } | null;
  error: string | null;
};

export type ProblemSummary = {
  slug: string;
  title: string;
  pattern: string;
  difficulty: "easy" | "medium" | "hard";
  status: "new" | "attempted" | "solved";
  xp: number;
  verified_cases: number;
};

export type ProblemDetail = Omit<ProblemSummary, "verified_cases"> & {
  statement: string;
  signature: string;
  examples: { args: unknown[]; expected: unknown }[];
  hidden_tests: number;
  starter_code: string;
  saved_code: string | null;
  verification: { cases_run: number; method: string; seed: number };
  history: { verdict: string; passed: number; total: number; is_submit: boolean; runtime_ms: number | null; created_at: string }[];
};

export type Verdict =
  | "accepted"
  | "wrong_answer"
  | "compilation_error"
  | "runtime_error"
  | "time_limit_exceeded"
  | "memory_limit_exceeded"
  | "execution_unavailable";

export type CodeResult = {
  verdict: Verdict;
  passed: number;
  total: number;
  public: { index: number; passed: boolean; args: unknown[]; expected: unknown; output: unknown }[];
  hidden_passed: number;
  hidden_total: number;
  first_failed_hidden: number | null;
  error: string | null;
  runtime_ms: number | null;
  executor: string;
  xp: number;
  status: ProblemSummary["status"];
};

export type ResumeClaim = { text: string; measurable: boolean; technologies: string[] };
export type Resume = { id: string; filename: string; extraction: string; claims: ResumeClaim[]; technologies: string[]; created_at: string };

export type InterviewQuestion = {
  index: number;
  kind: "behavioral" | "resume" | "technical" | "follow_up";
  text: string;
  claim?: string;
  slug?: string;
  problem?: ProblemDetail;
};

export type InterviewState = {
  id: string;
  role: string;
  role_label: string;
  kind: string;
  status: "active" | "completed";
  total: number;
  answered: number;
  question: InterviewQuestion | null;
  ai_feedback_available: boolean;
};

export type Metrics = {
  words: number;
  fillers: Record<string, number>;
  filler_total: number;
  source: string;
  duration_s?: number;
  speaking_s?: number;
  wpm?: number | null;
  pause_count?: number;
  long_pauses?: number;
  longest_pause_s?: number;
  fillers_per_min?: number | null;
};

export type Checks = {
  length: { words: number; ok: boolean };
  mentions_number: boolean;
  result_language: boolean;
  ownership: { i: number; we: number; ok: boolean };
  explains_measurement?: boolean;
  code?: { verdict: string; passed?: number; total?: number; hidden_passed?: number; hidden_total?: number; error?: string | null };
};

export type AiFeedback = {
  situation: number;
  task: number;
  action: number;
  result: number;
  specificity: number;
  strengths: string[];
  missing: string[];
  improvement: string;
  quote: string | null;
};

export type Turn = {
  index: number;
  question: string;
  source: InterviewQuestion["kind"];
  answer: string;
  input_mode: "voice" | "text";
  metrics: Metrics;
  checks: Checks;
  ai_feedback: AiFeedback | null;
};

export type InterviewReport = {
  id: string;
  role_label: string;
  kind: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  turns: Turn[];
  summary: {
    answers: number;
    voice_answers: number;
    avg_wpm: number | null;
    fillers_per_min: number | null;
    pauses: number;
    long_pauses: number;
    speaking_s: number;
    with_numbers: number;
    owned: number;
  };
  ai_scored: boolean;
  ai_available: boolean;
  focus: string[];
  ai_error?: string | null;
  xp?: number;
};

export type InterviewHistoryItem = { id: string; role: string; kind: string; status: string; started_at: string; completed_at: string | null; answers: number };

export type AudioMetrics = { duration_s: number; speaking_s: number; pauses_ms: number[] };

// ---------------------------------------------------------------- calls

export const api = {
  health: () => request<Health>("/health"),
  player: () => request<Player>("/api/player"),
  rename: (name: string) => post<Player>("/api/player/name", { name }),

  courses: () => request<Course[]>("/api/exam/courses"),
  uploadCourse: (file: File, name: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("name", name);
    return upload<UploadResult>("/api/exam/courses/upload", form);
  },
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  startFight: (courseId: string) => post<Fight>("/api/exam/sessions", { course_id: courseId }),
  fight: (id: string) => request<Fight>(`/api/exam/sessions/${id}`),
  nextQuestion: (id: string) => post<Fight>(`/api/exam/sessions/${id}/next`),
  hint: (id: string, questionId: string) => post<{ hint: string }>(`/api/exam/sessions/${id}/hint`, { question_id: questionId }),
  answer: (id: string, questionId: string, answer: string) => post<AnswerFeedback>(`/api/exam/sessions/${id}/answer`, { question_id: questionId, answer }),
  retreat: (id: string) => post<Fight>(`/api/exam/sessions/${id}/retreat`),
  results: (id: string) => request<FightResults>(`/api/exam/sessions/${id}/results`),
  preview: (text: string) => post<{ latex: string | null; error: string | null }>("/api/math/preview", { text }),

  problems: () => request<ProblemSummary[]>("/api/coding/problems"),
  problem: (slug: string) => request<ProblemDetail>(`/api/coding/problems/${slug}`),
  run: (slug: string, code: string) => post<CodeResult>(`/api/coding/problems/${slug}/run`, { code, language: "python" }),
  submit: (slug: string, code: string) => post<CodeResult>(`/api/coding/problems/${slug}/submit`, { code, language: "python" }),

  uploadResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return upload<Resume>("/api/interview/resume", form);
  },
  latestResume: () => request<Resume | null>("/api/interview/resume/latest"),
  interviews: () => request<InterviewHistoryItem[]>("/api/interview/sessions"),
  startInterview: (body: { role: string; kind: string; length: number; resume_id: string | null }) =>
    post<InterviewState>("/api/interview/sessions", body),
  interview: (id: string) => request<InterviewState>(`/api/interview/sessions/${id}`),
  interviewAnswer: (
    id: string,
    body: { index: number; transcript: string; input_mode: "voice" | "text"; audio?: AudioMetrics; code?: string },
  ) => post<{ turn: Turn; follow_up_added: string | null; session: InterviewState; xp: number }>(`/api/interview/sessions/${id}/answer`, body),
  finishInterview: (id: string) => post<InterviewReport>(`/api/interview/sessions/${id}/finish`),
  interviewReport: (id: string) => request<InterviewReport>(`/api/interview/sessions/${id}/report`),
};

/** Tell the HUD to refresh XP/level after something that can award XP. */
export function notifyProgress(xpGained = 0) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("reps:progress", { detail: { xp: xpGained } }));
}
