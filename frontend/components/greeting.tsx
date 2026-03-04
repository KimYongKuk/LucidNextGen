import { motion } from "framer-motion";

import { Workspace } from "@/lib/api/workspaces";
import { WorkspaceRecentHistory } from "@/components/workspace-recent-history";

function getTimeGreeting(): string {
  const hour = new Date().getHours();
  if (hour >= 6 && hour < 9) return "🐥좋은 아침이에요!";
  if (hour >= 9 && hour < 12) return "🛫활기찬 오전이에요!";
  if (hour >= 12 && hour < 13) return "🍕점심식사는 하셨나요?";
  if (hour >= 13 && hour < 17) return "🛫행복한 오후 보내세요!";
  if (hour >= 17 && hour < 19) return "🔥불타는 저녁이에요!";
  if (hour >= 19 && hour < 22) return "🔥불타는 야근이네요!";
  return "🔥늦은시간 고생많으시네요.";
}

export const Greeting = ({ workspace }: { workspace?: Workspace | null }) => {
  return (
    <div
      className="mx-auto mt-4 flex size-full max-w-3xl flex-col justify-center px-4 md:mt-16 md:px-8"
      key="overview"
    >
      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className="font-semibold text-xl md:text-2xl"
        exit={{ opacity: 0, y: 10 }}
        initial={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.5 }}
      >
        {workspace ? (
          <>
            <span className="text-primary">{workspace.name}</span> 워크스페이스와 대화중입니다.
          </>
        ) : (
          getTimeGreeting()
        )}
      </motion.div>
      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className="text-xl text-zinc-500 md:text-2xl"
        exit={{ opacity: 0, y: 10 }}
        initial={{ opacity: 0, y: 10 }}
        transition={{ delay: 0.6 }}
      >
        {workspace ? (
          <span className="text-base font-normal">{workspace.description || "이 워크스페이스를 위해 무엇을 도와드릴까요?"}</span>
        ) : (
          "오늘은 어떻게 도와드릴까요?"
        )}
      </motion.div>


      {
        workspace && (
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="mt-8 w-full"
            exit={{ opacity: 0, y: 10 }}
            initial={{ opacity: 0, y: 10 }}
            transition={{ delay: 0.7 }}
          >
            <WorkspaceRecentHistory workspace={workspace} />
          </motion.div>
        )
      }
    </div >
  );
};
