import React from "react";

export type Icons8Name =
  | "activity"
  | "applause"
  | "alert-triangle"
  | "book-add"
  | "book-open"
  | "bot"
  | "brain"
  | "building"
  | "camera"
  | "cancel-circle"
  | "check"
  | "check-circle"
  | "chevron-down"
  | "chevron-right"
  | "chevron-up"
  | "close"
  | "code"
  | "copy"
  | "cpu"
  | "database"
  | "desktop"
  | "dock-grid"
  | "door"
  | "eye"
  | "eye-off"
  | "file-text"
  | "folder-kanban"
  | "key"
  | "layout-list"
  | "lightbulb"
  | "live-tv"
  | "loader"
  | "lock"
  | "maximize"
  | "message"
  | "mic"
  | "mic-off"
  | "minimize"
  | "minus"
  | "monitor"
  | "orbit"
  | "palette"
  | "panel-right"
  | "party"
  | "play"
  | "radio"
  | "refresh"
  | "search"
  | "send"
  | "shield-alert"
  | "shield-check"
  | "sliders"
  | "sparkles"
  | "stop-all"
  | "stop-square"
  | "terminal"
  | "trash"
  | "user"
  | "volume-mute"
  | "volume-up"
  | "wrench"
  | "zap";

export interface Icons8IconProps {
  name: Icons8Name;
  size?: number;
  className?: string;
  title?: string;
}

export const Icons8Icon: React.FC<Icons8IconProps> = ({
  name,
  size,
  className = "w-4 h-4",
  title,
}) => {
  const url = `/static/icons8/${name}.png`;
  const style: React.CSSProperties = {
    display: "inline-block",
    flexShrink: 0,
    backgroundColor: "currentColor",
    maskImage: `url(${url})`,
    WebkitMaskImage: `url(${url})`,
    maskRepeat: "no-repeat",
    WebkitMaskRepeat: "no-repeat",
    maskPosition: "center",
    WebkitMaskPosition: "center",
    maskSize: "contain",
    WebkitMaskSize: "contain",
    ...(size ? { width: `${size}px`, height: `${size}px` } : {}),
  };

  return (
    <span
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      title={title}
      className={className}
      style={style}
    />
  );
};

export default Icons8Icon;

