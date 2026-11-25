// Real cases, verified 2026-11-25 (see docs/superpowers/plans/2026-11-25-landing-redesign.md).

// Hero: TCS AR 2023-24 p.56 prints FY24 ₹2,40,893 and FY23 ₹2,25,458 crore (+6.8%).
export const HERO_CASE = {
  company: 'TCS',
  document: 'Annual Report 2023-24',
  page: 56,
  question: "What was TCS's revenue in FY24?",
  answer: 'Consolidated revenue from operations was',
  figure: '₹2,40,893 crore',
  tail: ', up 6.8% year on year.',
  rowLabel: 'Revenue from operations',
  rowValue: '2,40,893',
};

// Final CTA chips: golden-set questions answered correctly, with the model's own citations, in eval v3.
export const CTA_EXAMPLES = [
  { label: 'HDFC merger date', question: 'When did the amalgamation of HDFC Limited with HDFC Bank become effective?' },
  { label: 'Infosys acquisitions FY25', question: 'Which acquisitions did the Infosys board approve in fiscal 2025?' },
  { label: 'HUL profit FY25', question: "What was Hindustan Unilever's profit after tax in FY2025?" },
];
