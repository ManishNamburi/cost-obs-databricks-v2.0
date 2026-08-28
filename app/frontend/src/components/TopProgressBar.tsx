import { useIsFetching } from "@tanstack/react-query";
import { C } from "@/theme";

export function TopProgressBar() {
  const fetching = useIsFetching();
  if (!fetching) return null;
  return (
    <>
      <style>{`@keyframes cobar{0%{left:-40%;width:40%}50%{left:20%;width:55%}100%{left:100%;width:40%}}`}</style>
      <div className="fixed left-0 top-0 z-[9999] h-0.5 w-full overflow-hidden" style={{ backgroundColor: C.coralTint }}>
        <div className="absolute h-full" style={{ backgroundColor: C.lava, animation: "cobar 1.1s ease-in-out infinite" }} />
      </div>
    </>
  );
}
