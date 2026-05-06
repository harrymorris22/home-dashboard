import { useHistory } from "../api/hooks";
import { HistoryChart } from "../components/HistoryChart";

export function History() {
  const { data } = useHistory(7);
  return (
    <div className="space-y-4">
      <h1 className="font-display text-3xl uppercase tracking-tight text-primary">History</h1>
      <HistoryChart data={data} />
    </div>
  );
}
