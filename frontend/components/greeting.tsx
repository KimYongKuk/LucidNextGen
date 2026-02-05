import { motion } from "framer-motion";

import { Workspace } from "@/lib/api/workspaces";
import { WorkspaceRecentHistory } from "@/components/workspace-recent-history";

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
          "🌞Hi There!"
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
