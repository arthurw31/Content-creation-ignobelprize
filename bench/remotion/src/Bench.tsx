import React from "react";
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FPS = 30;
const s = (seconds: number) => Math.round(seconds * FPS);

const YELLOW = "#ffc700";
const CREAM = "#f7f6f2";
const FONT = '"DejaVu Sans", sans-serif';

const vignette: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  background:
    "radial-gradient(ellipse at 50% 40%, rgba(0,0,0,0) 30%, rgba(0,0,0,.75) 100%)",
};

const photoStyle = (scale: number, xPercent = 0): React.CSSProperties => ({
  position: "absolute",
  top: "50%",
  left: "50%",
  width: "120%",
  height: "120%",
  objectFit: "cover",
  transform: `translate(-50%, -50%) translateX(${xPercent}%) scale(${scale})`,
});

/** Scene 1 — archive photo pushes in, lower third slides up then leaves. */
const SceneOne: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = interpolate(frame, [0, s(3.4)], [1.0, 1.16]);

  const enter = spring({ frame: frame - s(0.25), fps, config: { damping: 200 } });
  const exit = interpolate(frame, [s(2.95), s(3.3)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = enter * (1 - exit);
  const y = interpolate(enter, [0, 1], [60, 0]) - exit * 40;

  return (
    <AbsoluteFill>
      <Img src={staticFile("photo-a.jpg")} style={photoStyle(scale)} />
      <div style={vignette} />
      <div
        style={{
          position: "absolute",
          left: 70,
          bottom: 460,
          borderLeft: `10px solid ${YELLOW}`,
          paddingLeft: 34,
          opacity,
          transform: `translateY(${y}px)`,
        }}
      >
        <div
          style={{
            color: YELLOW,
            fontSize: 34,
            fontWeight: 700,
            letterSpacing: 2,
            marginBottom: 18,
            fontFamily: FONT,
          }}
        >
          IG NOBEL · REPRODUCTION · 2016
        </div>
        <div
          style={{
            color: CREAM,
            fontSize: 84,
            fontWeight: 700,
            lineHeight: 1.06,
            fontFamily: FONT,
            textShadow: "0 6px 30px rgba(0,0,0,.6)",
          }}
        >
          He put polyester pants
          <br />
          on 75 rats
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Scene 2 — photo pans while the stat counts up and the bar fills. */
const SceneTwo: React.FC = () => {
  const frame = useCurrentFrame();

  const scale = interpolate(frame, [0, s(2.8)], [1.18, 1.02]);
  const pan = interpolate(frame, [0, s(2.8)], [-3, 3]);

  const count = Math.round(
    interpolate(frame, [s(0.3), s(1.4)], [0, 75], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: (t) => 1 - Math.pow(1 - t, 2),
    }),
  );
  const barWidth = interpolate(frame, [s(0.4), s(1.8)], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: (t) => 1 - Math.pow(1 - t, 2),
  });

  return (
    <AbsoluteFill>
      <Img src={staticFile("photo-b.jpg")} style={photoStyle(scale, pan)} />
      <div style={vignette} />
      <div style={{ position: "absolute", left: 70, bottom: 520, width: 940 }}>
        <div
          style={{
            color: YELLOW,
            fontSize: 300,
            fontWeight: 700,
            lineHeight: 0.9,
            fontFamily: FONT,
          }}
        >
          {count}
        </div>
        <div
          style={{
            color: CREAM,
            fontSize: 36,
            fontWeight: 700,
            letterSpacing: 3,
            margin: "24px 0 30px",
            fontFamily: FONT,
          }}
        >
          RATS · FIVE GROUPS · TWELVE MONTHS
        </div>
        <div
          style={{
            height: 18,
            background: "rgba(255,255,255,.16)",
            borderRadius: 9,
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${barWidth}%`,
              background: YELLOW,
              borderRadius: 9,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Scene 3 — the twist card punches in. */
const SceneThree: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({
    frame: frame - s(0.05),
    fps,
    config: { damping: 12, stiffness: 200 },
  });

  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 45%, #7a2418 0%, #2b0f0c 70%)",
        }}
      />
      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          color: "#ff5c3c",
          fontSize: 140,
          fontWeight: 700,
          lineHeight: 1.02,
          fontFamily: FONT,
          opacity: pop,
          transform: `scale(${interpolate(pop, [0, 1], [0.82, 1])})`,
        }}
      >
        STATIC
        <br />
        ELECTRICITY
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

/** Yellow panel sweeps across to cover the cut. */
const Wipe: React.FC = () => {
  const frame = useCurrentFrame();
  const x = interpolate(frame, [0, s(0.25), s(0.5)], [-100, 0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{ background: YELLOW, transform: `translateX(${x}%)` }}
    />
  );
};

const CAPTIONS: [number, string][] = [
  [0.0, "seventy-five rats"],
  [1.4, "five groups"],
  [2.4, "twelve months"],
  [3.6, "cotton was fine"],
  [5.0, "polyester was not"],
  [6.3, "here is why"],
];

export const Bench: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const caption =
    [...CAPTIONS].reverse().find(([t]) => frame >= s(t))?.[1] ?? "";
  const progress = (frame / durationInFrames) * 100;

  return (
    <AbsoluteFill style={{ background: "#0a0a0c" }}>
      <Sequence from={0} durationInFrames={s(3.4)}>
        <SceneOne />
      </Sequence>
      <Sequence from={s(3.4)} durationInFrames={s(2.8)}>
        <SceneTwo />
      </Sequence>
      <Sequence from={s(6.2)} durationInFrames={s(1.8)}>
        <SceneThree />
      </Sequence>
      <Sequence from={s(3.15)} durationInFrames={s(0.5)}>
        <Wipe />
      </Sequence>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 300,
          textAlign: "center",
          color: CREAM,
          fontSize: 62,
          fontWeight: 700,
          fontFamily: FONT,
          textShadow: "0 4px 18px rgba(0,0,0,.85)",
        }}
      >
        {caption}
      </div>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: 10,
          background: "rgba(255,255,255,.14)",
        }}
      >
        <div
          style={{ height: "100%", width: `${progress}%`, background: YELLOW }}
        />
      </div>
    </AbsoluteFill>
  );
};
