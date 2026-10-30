const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});
const inrRound = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const compact = new Intl.NumberFormat("en-IN", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export const formatINR = (n: number) => inr.format(n);
export const formatINRRound = (n: number) => inrRound.format(n);
export const formatCompact = (n: number) => `₹${compact.format(n)}`;

const pad = (n: number) => String(n).padStart(2, "0");

export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export const currentMonth = () => todayISO().slice(0, 7);

export function addMonths(month: string, n: number): string {
  const [y, m] = month.split("-").map(Number);
  const idx = y * 12 + (m - 1) + n;
  return `${Math.floor(idx / 12)}-${pad((idx % 12) + 1)}`;
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
const MONTHS_LONG = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const monthLabel = (month: string) =>
  `${MONTHS_LONG[Number(month.slice(5, 7)) - 1]} ${month.slice(0, 4)}`;
export const shortMonth = (month: string) =>
  MONTHS[Number(month.slice(5, 7)) - 1];

export function dayHeading(date: string): string {
  const t = todayISO();
  if (date === t) return "Today";
  const y = new Date();
  y.setDate(y.getDate() - 1);
  if (
    date === `${y.getFullYear()}-${pad(y.getMonth() + 1)}-${pad(y.getDate())}`
  )
    return "Yesterday";
  const [yy, mm, dd] = date.split("-").map(Number);
  const d = new Date(yy, mm - 1, dd);
  return `${DAYS[d.getDay()]}, ${dd} ${MONTHS[mm - 1]}`;
}

export function shortDate(date: string): string {
  const [, mm, dd] = date.split("-").map(Number);
  return `${dd} ${MONTHS[mm - 1]}`;
}

export function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}
