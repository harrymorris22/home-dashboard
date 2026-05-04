import { useHistory } from "../api/hooks";
import { HistoryChart } from "../components/HistoryChart";

export function History() {
  const { data } = useHistory(7);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">History</h1>
      <HistoryChart data={data} />
    </div>
  );
}
