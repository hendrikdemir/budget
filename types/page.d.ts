// For the type checks of the page's scripts (jsconfig.json): the page looks up elements by
// selectors it knows and uses them as the HTML elements they are (inputs, buttons, dialogs).
// Saying so here keeps the checks on what matters: names, arguments and values.
interface ParentNode {
  querySelector(selectors: string): any;
  querySelectorAll(selectors: string): NodeListOf<any>;
}
interface Element {
  closest(selectors: string): any;
}
// An event's target is an element of the page here (never the window itself).
interface EventTarget {
  closest(selectors: string): any;
}
