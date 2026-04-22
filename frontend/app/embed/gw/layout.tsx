import { DataStreamProvider } from "@/components/data-stream-provider";

export default function EmbedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <DataStreamProvider>
      {children}
    </DataStreamProvider>
  );
}
