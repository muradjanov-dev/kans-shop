// Categories rarely have photos, so each tile gets a drawn icon chosen from its name
// (Uzbek or Russian, any case) instead of an empty grey square.
type IconKind =
  | "office"
  | "building"
  | "stamp"
  | "art"
  | "home"
  | "pen"
  | "book"
  | "paper"
  | "folder"
  | "school"
  | "default";

const RULES: Array<[RegExp, IconKind]> = [
  [/штемп|печат|shtamp|muhr/i, "stamp"],
  [/творч|ijod|рисов|art|bo'?yoq/i, "art"],
  [/папк|архив|papka|arxiv|fayl/i, "folder"],
  [/книг|kitob|book/i, "book"],
  [/бумаж|бумаг|qog['‘ʻ]?oz|paper/i, "paper"],
  [/письм|ручк|yozuv|ruchka|pen|qalam/i, "pen"],
  [/школ|maktab|school/i, "school"],
  [/быт|uy-ro|maishiy|home|xo['‘ʻ]?jalik/i, "home"],
  [/строит|qurilish|build/i, "building"],
  [/офис|ofis|office/i, "office"],
];

export function categoryIconKind(name: string): IconKind {
  return RULES.find(([pattern]) => pattern.test(name))?.[1] ?? "default";
}

const PATHS: Record<IconKind, string> = {
  office: "M4 8h16v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Zm5 0V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M4 13h16",
  building: "M4 20V9l8-5 8 5v11M9 20v-6h6v6M3 20h18",
  stamp: "M9 4h6v5l2 3H7l2-3V4Zm-4 9h14v4H5v-4Zm2 7h10",
  art: "M12 4a8 8 0 1 0 0 16c1.1 0 1.6-.9 1.2-1.8-.5-1 .2-2.2 1.3-2.2H17a3 3 0 0 0 3-3c0-5-3.6-9-8-9ZM8 11h.01M11 7.5h.01M15.5 8.5h.01",
  home: "M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1v-8Z",
  pen: "m14.5 4.5 5 5L9 20H4v-5L14.5 4.5Zm-2 2 5 5",
  book: "M5 4.5A2.5 2.5 0 0 1 7.5 2H19v16H7.5A2.5 2.5 0 0 0 5 20.5v-16Zm0 16A2.5 2.5 0 0 1 7.5 18H19v4H7.5A2.5 2.5 0 0 1 5 20.5ZM9 7h6",
  paper: "M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm7 0v5h5M9 13h6M9 17h6",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z",
  school: "m3 9 9-5 9 5-9 5-9-5Zm4 2.5V16c0 1.7 2.2 3 5 3s5-1.3 5-3v-4.5M21 9v5",
  default: "M5 5h6v6H5V5Zm8 0h6v6h-6V5Zm-8 8h6v6H5v-6Zm8 8 3-6 3 6h-6Z",
};

export function CategoryIcon({ name, className = "" }: { name: string; className?: string }) {
  return (
    <svg aria-hidden="true" className={className} fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" viewBox="0 0 24 24">
      <path d={PATHS[categoryIconKind(name)]} />
    </svg>
  );
}
