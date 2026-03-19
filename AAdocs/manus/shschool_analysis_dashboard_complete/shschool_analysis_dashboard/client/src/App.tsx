import { Toaster } from "@/components/ui/sonner.tsx";
import { TooltipProvider } from "@/components/ui/tooltip.tsx";
import NotFound from "@/pages/NotFound.tsx";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary.tsx";
import { ThemeProvider } from "./contexts/ThemeContext.tsx";
import Home from "./pages/Home.tsx";
import SWOTDetail from "./pages/SWOTDetail.tsx";
import ComplianceDetail from "./pages/ComplianceDetail.tsx";
import SecurityDetail from "./pages/SecurityDetail.tsx";
import Roadmap from "./pages/Roadmap.tsx";


function Router() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      <Route path="/swot" component={SWOTDetail} />
      <Route path="/compliance" component={ComplianceDetail} />
      <Route path="/security" component={SecurityDetail} />
      <Route path="/roadmap" component={Roadmap} />
      <Route path="/404" component={NotFound} />
      {/* Final fallback route */}
      <Route component={NotFound} />
    </Switch>
  );
}

// NOTE: About Theme
// - First choose a default theme according to your design style (dark or light bg), than change color palette in index.css
//   to keep consistent foreground/background color across components
// - If you want to make theme switchable, pass `switchable` ThemeProvider and use `useTheme` hook

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider
        defaultTheme="light"
        // switchable
      >
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
