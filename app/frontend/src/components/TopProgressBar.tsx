import { useIsFetching } from "@tanstack/react-query";

// A slim indeterminate progress bar pinned to the top of the viewport, shown
// whenever any React Query fetch is in flight. Gives global "refreshing" feedback
// when filters change (workspace, data source, date) or a source is added — so the
// user always sees that the visuals are updating, not just when the data swaps in.
export function TopProgressBar() {
  const fetching = useIsFetching();
  if (!fetching) return null;
  return (
    <>
      <style>{`@keyframes cobar{0%{left:-40%;width:40%}50%{left:20%;width:55%}100%{left:100%;width:40%}}`}</style>
      <div className="fixed left-0 top-0 z-[9999] h-0.5 w-full overflow-hidden" style={{ backgroundColor: "#FFE3DD" }}>
        <div className="absolute h-full" style={{ backgroundColor: "#FF3621", animation: "cobar 1.1s ease-in-out infinite" }} />
      </div>
    </>
  );
}
