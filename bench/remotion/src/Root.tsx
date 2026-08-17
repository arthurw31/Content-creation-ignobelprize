import { Composition } from "remotion";
import { Bench } from "./Bench";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="bench"
    component={Bench}
    durationInFrames={240}
    fps={30}
    width={1080}
    height={1920}
  />
);
