import { useProjectStore } from "../stores/projectStore";
import { useViewStore } from "../stores/viewStore";

interface AddressLinkProps {
  target: string; // function name or address like "sub_1511", "0x1234", "main"
  children?: React.ReactNode;
}

export function AddressLink({ target, children }: AddressLinkProps) {
  const { activeProjectId } = useProjectStore();
  const { navigateTo } = useViewStore();

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (activeProjectId) {
      navigateTo(activeProjectId, target);
    }
  };

  return (
    <span className="addr-link" onClick={handleClick} title={`Go to ${target}`}>
      {children || target}
    </span>
  );
}
