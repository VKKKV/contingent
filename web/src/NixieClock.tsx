import { useEffect, useState } from "react";
import { startUtcClock, utcClock } from "./utcClock";

export default function NixieClock() {
  const [timestamp, setTimestamp] = useState(() => Date.now());
  useEffect(() => startUtcClock(setTimestamp), []);
  const clock = utcClock(timestamp);

  return (
    <section className="nixie-clock" aria-label="UTC clock" aria-live="off">
      <p className="meter-unit" data-testid="meter-label">
        UTC / HH.MM.SS
      </p>
      <time className="nixie-time" dateTime={clock.dateTime}>
        <span
          className="nixie-bank"
          data-testid="meter-digits"
          aria-hidden="true"
        >
          {[...clock.time].map((digit, index) => (
            <img
              className="nixie-digit"
              key={index}
              src={`/vendor/divergencemeter/${digit === "." ? "p" : digit}.png`}
              alt=""
              width={130}
              height={384}
              draggable={false}
            />
          ))}
        </span>
        <span className="nixie-readable-time">
          {clock.time.replaceAll(".", ":")} UTC · {clock.calendarDate}
        </span>
        <span className="meter-date" aria-hidden="true">
          {clock.calendarDate}
        </span>
      </time>
    </section>
  );
}
