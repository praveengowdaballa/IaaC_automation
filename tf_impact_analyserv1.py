#!/usr/bin/env python3
"""
Enterprise Terraform Impact Analyser (v2.0)
High-performance, filter-enabled change detector for large-scale plans.
Provides a dynamic HTML dashboard with client-side filtering.
"""

import json
import argparse
import re
import logging
import sys
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("TF-Impact")

@dataclass
class ResourceChange:
    address: str
    type: str
    name: str
    module: str
    provider: str
    actions: List[str]
    risk_level: str
    change_summary: str

class FilterEngine:
    """Enterprise filtering logic for large-scale infrastructure"""
    def __init__(self, include_types=None, exclude_types=None, 
                 modules=None, providers=None, address_regex=None):
        self.include_types = set(include_types) if include_types else None
        self.exclude_types = set(exclude_types) if exclude_types else None
        self.modules = set(modules) if modules else None
        self.providers = set(providers) if providers else None
        self.address_pattern = re.compile(address_regex) if address_regex else None

    def should_include(self, resource_addr: str, r_type: str, 
                       module: str, provider: str) -> bool:
        if self.include_types and r_type not in self.include_types: return False
        if self.exclude_types and r_type in self.exclude_types: return False
        if self.modules and not any(module.startswith(m) for m in self.modules): return False
        if self.providers and provider not in self.providers: return False
        if self.address_pattern and not self.address_pattern.search(resource_addr): return False
        return True

class RiskAnalyzer:
    """Identifies dangerous changes based on resource sensitivity"""
    CRITICAL_TYPES = {
        'aws_db_instance', 'aws_rds_cluster', 'google_sql_database_instance',
        'azurerm_postgresql_server', 'aws_s3_bucket', 'google_storage_bucket',
        'aws_iam_role', 'aws_kms_key', 'kubernetes_namespace', 'aws_route53_zone'
    }

    @staticmethod
    def assess(resource_type: str, actions: List[str]) -> str:
        is_delete = 'delete' in actions
        is_replace = 'create' in actions and 'delete' in actions
        
        if resource_type in RiskAnalyzer.CRITICAL_TYPES:
            return "CRITICAL" if (is_delete or is_replace) else "HIGH"
        
        if is_delete or is_replace:
            return "HIGH"
        if 'update' in actions:
            return "MEDIUM"
        return "LOW"

class EnterpriseTFDetector:
    def __init__(self, plan_file: str, filter_engine: FilterEngine):
        self.plan_file = plan_file
        self.filter_engine = filter_engine
        self.risk_analyzer = RiskAnalyzer()
        self.data = self._load_plan(plan_file)
        
    def _load_plan(self, filepath: str) -> Dict:
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load plan file: {e}")
            sys.exit(1)

    def _detect_provider(self, resource_type: str) -> str:
        parts = resource_type.split('_', 1)
        return parts[0] if len(parts) > 1 else 'other'

    def analyze(self) -> Dict[str, Any]:
        logger.info(f"Analyzing {self.plan_file}...")
        
        results = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'tf_version': self.data.get('terraform_version', 'Unknown'),
                'plan_id': self.data.get('format_version', 'N/A')
            },
            'changes': [],
            'stats': defaultdict(int),
            'risk_summary': defaultdict(int),
            'by_module': defaultdict(lambda: defaultdict(int))
        }

        resource_changes = self.data.get('resource_changes', [])
        
        for change in resource_changes:
            addr = change.get('address')
            r_type = change.get('type')
            module = change.get('module_address', 'root')
            provider = self._detect_provider(r_type)
            actions = change.get('change', {}).get('actions', [])

            if 'no-op' in actions or not actions or actions == ['read']:
                continue

            if not self.filter_engine.should_include(addr, r_type, module, provider):
                continue

            risk = self.risk_analyzer.assess(r_type, actions)
            primary_action = "replace" if ('create' in actions and 'delete' in actions) else actions[0]
            
            res_obj = ResourceChange(
                address=addr,
                type=r_type,
                name=change.get('name'),
                module=module,
                provider=provider,
                actions=actions,
                risk_level=risk,
                change_summary=" -> ".join(actions)
            )
            
            results['changes'].append(asdict(res_obj))
            results['stats'][primary_action] += 1
            results['risk_summary'][risk] += 1
            results['by_module'][module][primary_action] += 1

        return results

class EnterpriseVisualizer:
    def __init__(self, analysis_results: Dict):
        self.results = analysis_results

    def generate_html(self, output_file: str):
        """Generates a standalone HTML dashboard with client-side filtering"""
        json_data = json.dumps(self.results)
        
        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TF Impact Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .risk-CRITICAL {{ border-left: 5px solid #ef4444; background: rgba(239, 68, 68, 0.05); }}
        .risk-HIGH {{ border-left: 5px solid #f97316; background: rgba(249, 115, 22, 0.05); }}
        .risk-MEDIUM {{ border-left: 5px solid #f59e0b; }}
        .risk-LOW {{ border-left: 5px solid #10b981; }}
    </style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen pb-20">
    <div class="max-w-7xl mx-auto px-6 py-10">
        <header class="flex justify-between items-center mb-10 border-b border-slate-700 pb-8">
            <div>
                <h1 class="text-4xl font-extrabold text-white tracking-tight">Terraform Impact Dashboard</h1>
                <p class="text-slate-400 mt-2 font-medium">Enterprise Infrastructure Change Analysis</p>
            </div>
            <div class="text-right">
                <div class="text-xs uppercase tracking-widest text-slate-500 font-bold">Report Generated</div>
                <div class="text-slate-300 font-mono">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
        </header>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-6 mb-10">
            <div class="bg-slate-800 p-6 rounded-2xl border border-slate-700 shadow-lg">
                <div class="text-slate-500 text-xs font-bold uppercase mb-1">Create</div>
                <div class="text-3xl font-bold text-emerald-500">{self.results['stats']['create']}</div>
            </div>
            <div class="bg-slate-800 p-6 rounded-2xl border border-slate-700 shadow-lg">
                <div class="text-slate-500 text-xs font-bold uppercase mb-1">Update</div>
                <div class="text-3xl font-bold text-amber-500">{self.results['stats']['update']}</div>
            </div>
            <div class="bg-slate-800 p-6 rounded-2xl border border-slate-700 shadow-lg">
                <div class="text-slate-500 text-xs font-bold uppercase mb-1">Replace</div>
                <div class="text-3xl font-bold text-violet-500">{self.results['stats']['replace']}</div>
            </div>
            <div class="bg-slate-800 p-6 rounded-2xl border border-slate-700 shadow-lg">
                <div class="text-slate-500 text-xs font-bold uppercase mb-1">Delete</div>
                <div class="text-3xl font-bold text-red-500">{self.results['stats']['delete']}</div>
            </div>
        </div>

        <div class="bg-slate-800 p-8 rounded-2xl mb-10 border border-slate-700 shadow-2xl">
            <h3 class="text-sm font-bold text-slate-400 uppercase tracking-widest mb-6">Interactive Filters</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div class="space-y-2">
                    <label class="text-xs font-bold text-slate-500 uppercase">Search Resources</label>
                    <input type="text" id="searchBox" placeholder="Search address, type, or module..." 
                           class="w-full bg-slate-900 border-slate-700 border rounded-xl p-3 text-sm focus:ring-2 focus:ring-blue-500 outline-none transition-all">
                </div>
                <div class="space-y-2">
                    <label class="text-xs font-bold text-slate-500 uppercase">Risk Threshold</label>
                    <select id="riskFilter" class="w-full bg-slate-900 border-slate-700 border rounded-xl p-3 text-sm outline-none">
                        <option value="ALL">Show All Risks</option>
                        <option value="CRITICAL">Critical Only</option>
                        <option value="HIGH">High & Above</option>
                    </select>
                </div>
                <div class="space-y-2">
                    <label class="text-xs font-bold text-slate-500 uppercase">Filter Action</label>
                    <select id="actionFilter" class="w-full bg-slate-900 border-slate-700 border rounded-xl p-3 text-sm outline-none">
                        <option value="ALL">All Actions</option>
                        <option value="create">Create</option>
                        <option value="update">Update</option>
                        <option value="replace">Replace</option>
                        <option value="delete">Delete</option>
                    </select>
                </div>
            </div>
        </div>

        <div class="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden shadow-2xl">
            <div id="resource-list" class="divide-y divide-slate-700">
                </div>
        </div>
    </div>

    <script>
        const data = {json_data};
        const listContainer = document.getElementById('resource-list');

        function updateUI() {{
            const searchTerm = document.getElementById('searchBox').value.toLowerCase();
            const riskLevel = document.getElementById('riskFilter').value;
            const actionType = document.getElementById('actionFilter').value;

            const filtered = data.changes.filter(item => {{
                const matchesSearch = item.address.toLowerCase().includes(searchTerm) || 
                                    item.type.toLowerCase().includes(searchTerm);
                
                const matchesRisk = riskLevel === 'ALL' || 
                                   (riskLevel === 'HIGH' ? (item.risk_level === 'HIGH' || item.risk_level === 'CRITICAL') : item.risk_level === riskLevel);
                
                const matchesAction = actionType === 'ALL' || item.actions.includes(actionType);
                
                return matchesSearch && matchesRisk && matchesAction;
            }});

            if (filtered.length === 0) {{
                listContainer.innerHTML = '<div class="p-20 text-center text-slate-500 font-medium">No resources match your filters</div>';
                return;
            }}

            listContainer.innerHTML = filtered.map(item => `
                <div class="p-6 hover:bg-slate-700/20 transition-all risk-${{item.risk_level}} flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div class="flex-1">
                        <div class="flex items-center gap-3 mb-1">
                            <span class="text-xs font-mono font-bold text-slate-500 bg-slate-900 px-2 py-0.5 rounded border border-slate-700">${{item.type}}</span>
                            <span class="text-xs font-bold uppercase tracking-tighter ${{item.risk_level === 'CRITICAL' ? 'text-red-500' : (item.risk_level === 'HIGH' ? 'text-orange-500' : 'text-slate-400')}}">
                                ${{item.risk_level}} RISK
                            </span>
                        </div>
                        <h4 class="text-blue-400 font-mono text-sm font-semibold mb-1 truncate"># ${{item.address}}</h4>
                        <div class="text-xs text-slate-500">Module Path: <span class="text-slate-400">${{item.module}}</span></div>
                    </div>
                    <div class="flex flex-col items-end gap-2">
                        <div class="flex gap-1">
                            ${{item.actions.map(a => `
                                <span class="px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border
                                    ${{a === 'create' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' : 
                                      a === 'delete' ? 'bg-red-500/10 text-red-500 border-red-500/20' : 
                                      'bg-blue-500/10 text-blue-400 border-blue-500/20'}}">
                                    ${{a}}
                                </span>
                            `).join('')}}
                        </div>
                        <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Provider: ${{item.provider}}</div>
                    </div>
                </div>
            `).join('');
        }}

        document.getElementById('searchBox').addEventListener('input', updateUI);
        document.getElementById('riskFilter').addEventListener('change', updateUI);
        document.getElementById('actionFilter').addEventListener('change', updateUI);
        
        // Initial render
        updateUI();
    </script>
</body>
</html>
        """
        with open(output_file, 'w') as f:
            f.write(html_template)
        print(f"✅ Dashboard generated: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Enterprise TF Impact Dashboard Generator')
    parser.add_argument('plan', help='Terraform plan JSON file')
    parser.add_argument('--output', default='tf_report.html', help='Output HTML filename')
    parser.add_argument('--provider', nargs='+', help='Initial filter by provider')
    parser.add_argument('--module', nargs='+', help='Initial filter by module prefix')
    
    args = parser.parse_args()

    # Pre-filtering engine (CLI level)
    engine = FilterEngine(providers=args.provider, modules=args.module)
    
    detector = EnterpriseTFDetector(args.plan, engine)
    results = detector.analyze()
    
    visualizer = EnterpriseVisualizer(results)
    visualizer.generate_html(args.output)

    print("\nSummary:")
    print(f"  - Total Changes detected: {sum(results['stats'].values())}")
    print(f"  - Critical Risks: {results['risk_summary']['CRITICAL']}")
    print(f"  - High Risks: {results['risk_summary']['HIGH']}")

if __name__ == "__main__":
    main()
