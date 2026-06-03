"""
Production-ready backtesting bot with robust error handling and validation.
"""

import pandas as pd
import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import argparse
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'backtest_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtest parameters."""
    threshold: int = 1
    initial_capital: float = 10000.0
    risk_pct: float = 0.05
    fee_pct: float = 0.005
    filtered_folder: str = "step3_filtered"
    output_file: str = None  # Will be auto-generated if None
    
    def __post_init__(self):
        """Validate configuration parameters."""
        if self.initial_capital <= 0:
            raise ValueError(f"Initial capital must be positive, got {self.initial_capital}")
        if not 0 < self.risk_pct <= 1:
            raise ValueError(f"Risk percentage must be between 0 and 1, got {self.risk_pct}")
        if not 0 <= self.fee_pct <= 1:
            raise ValueError(f"Fee percentage must be between 0 and 1, got {self.fee_pct}")
        if self.threshold < 0:
            raise ValueError(f"Threshold must be non-negative, got {self.threshold}")
        
        # Auto-generate output filename if not provided
        if self.output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_file = f"backtest_results_{timestamp}.csv"


@dataclass
class BacktestStats:
    """Statistics from backtest run."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    buy_trades: int = 0
    sell_trades: int = 0
    total_pnl: float = 0.0
    final_balance: float = 0.0
    max_equity: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    buy_win_rate: float = 0.0
    sell_win_rate: float = 0.0
    yearly_stats: Dict = None
    
    def __post_init__(self):
        if self.yearly_stats is None:
            self.yearly_stats = {}


class TradeDataValidator:
    """Validates trade data schema and content."""
    
    REQUIRED_COLUMNS = ['date', 'time', 'type', 'entry', 'stop_loss', 'distance', 'reward_risk']
    VALID_TRADE_TYPES = ['buy', 'sell']
    
    @staticmethod
    def validate_dataframe(df: pd.DataFrame, source: str = "unknown") -> Tuple[bool, List[str]]:
        """
        Validate DataFrame schema and content.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check if DataFrame is empty
        if df is None or df.empty:
            errors.append(f"DataFrame from {source} is empty")
            return False, errors
        
        # Check required columns
        missing_cols = set(TradeDataValidator.REQUIRED_COLUMNS) - set(df.columns)
        if missing_cols:
            errors.append(f"Missing required columns in {source}: {missing_cols}")
        
        # Check for null values in critical columns
        for col in TradeDataValidator.REQUIRED_COLUMNS:
            if col in df.columns:
                null_count = df[col].isnull().sum()
                if null_count > 0:
                    errors.append(f"Column '{col}' has {null_count} null values in {source}")
        
        # Validate trade types
        if 'type' in df.columns:
            invalid_types = df[~df['type'].str.lower().isin(TradeDataValidator.VALID_TRADE_TYPES)]
            if not invalid_types.empty:
                errors.append(f"Invalid trade types found in {source}: {invalid_types['type'].unique()}")
        
        # Validate numeric columns
        numeric_cols = ['entry', 'stop_loss', 'distance']
        for col in numeric_cols:
            if col in df.columns:
                try:
                    pd.to_numeric(df[col], errors='raise')
                except (ValueError, TypeError) as e:
                    errors.append(f"Column '{col}' contains non-numeric values in {source}: {str(e)}")
        
        return len(errors) == 0, errors


class TradeDataLoader:
    """Handles loading and preprocessing of trade data."""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.validator = TradeDataValidator()
    
    def load_survived_trades(self) -> Optional[pd.DataFrame]:
        """
        Load all survived trades from the filtered folder.
        
        Returns:
            DataFrame with all trades, or None if loading fails
        """
        threshold_path = Path(self.config.filtered_folder) / str(self.config.threshold)
        
        # Validate path exists
        if not threshold_path.exists():
            logger.error(f"Threshold folder does not exist: {threshold_path}")
            return None
        
        if not threshold_path.is_dir():
            logger.error(f"Threshold path is not a directory: {threshold_path}")
            return None
        
        # Find all CSV files
        csv_files = list(threshold_path.glob("*.csv"))
        
        if not csv_files:
            logger.warning(f"No CSV files found in {threshold_path}")
            return None
        
        logger.info(f"Found {len(csv_files)} CSV files in {threshold_path}")
        
        # Load and validate each CSV
        valid_dataframes = []
        for csv_file in csv_files:
            try:
                df = pd.read_csv(csv_file)
                is_valid, errors = self.validator.validate_dataframe(df, str(csv_file))
                
                if is_valid:
                    valid_dataframes.append(df)
                    logger.info(f"Loaded {len(df)} trades from {csv_file.name}")
                else:
                    logger.warning(f"Skipping invalid file {csv_file.name}: {errors}")
                    
            except Exception as e:
                logger.error(f"Failed to load {csv_file.name}: {str(e)}")
                continue
        
        if not valid_dataframes:
            logger.error("No valid trade data loaded")
            return None
        
        # Merge all dataframes
        try:
            merged_df = pd.concat(valid_dataframes, ignore_index=True)
            logger.info(f"Merged {len(merged_df)} total trades from {len(valid_dataframes)} files")
        except Exception as e:
            logger.error(f"Failed to merge dataframes: {str(e)}")
            return None
        
        # Remove duplicates
        initial_count = len(merged_df)
        merged_df = merged_df.drop_duplicates()
        if len(merged_df) < initial_count:
            logger.info(f"Removed {initial_count - len(merged_df)} duplicate trades")
        
        # Parse and sort by datetime
        try:
            merged_df['datetime'] = pd.to_datetime(
                merged_df['date'].astype(str) + ' ' + merged_df['time'].astype(str),
                errors='coerce'
            )
            
            # Check for parsing failures
            null_datetime = merged_df['datetime'].isnull().sum()
            if null_datetime > 0:
                logger.warning(f"Failed to parse {null_datetime} datetime values, dropping those rows")
                merged_df = merged_df.dropna(subset=['datetime'])
            
            merged_df = merged_df.sort_values('datetime').reset_index(drop=True)
            logger.info(f"Sorted {len(merged_df)} trades by datetime")
            
        except Exception as e:
            logger.error(f"Failed to parse/sort datetime: {str(e)}")
            return None
        
        return merged_df


class BacktestEngine:
    """Core backtesting engine with PnL calculation."""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
    
    def calculate_trade_pnl(
        self,
        row: pd.Series,
        account_balance: float
    ) -> Tuple[float, bool]:
        """
        Calculate PnL for a single trade with 1:1 exit strategy.
        
        - Risk per trade: 5% of current equity
        - Fee per trade: 0.5% of current equity
        - If reward_risk >= 1.0: trade hits 1:1 TP → win risk_amount (not risk_amount * reward_risk)
        - If reward_risk == "SL": trade hits stop loss → lose risk_amount
        
        Returns:
            Tuple of (pnl, is_win)
        """
        try:
            # Calculate risk amount based on current equity
            risk_amount = account_balance * self.config.risk_pct
            
            # Calculate fee based on current equity
            fee = account_balance * self.config.fee_pct
            
            # Parse reward_risk
            reward_risk_str = str(row['reward_risk']).strip().upper()
            
            # Determine if trade is a win or loss
            # Exit at 1:1 RR — win returns exactly risk_amount, not risk_amount * reward_risk
            if reward_risk_str == "SL":
                # Stop loss hit: lose risk_amount + fee
                is_win = False
                pnl = -(risk_amount + fee)
            else:
                try:
                    reward_risk = float(reward_risk_str)
                    if reward_risk >= 1.0:
                        # Hit 1:1 take profit: win risk_amount - fee
                        is_win = True
                        pnl = risk_amount - fee
                    else:
                        # Positive RR but below 1.0 — treat as stop loss hit
                        is_win = False
                        pnl = -(risk_amount + fee)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid reward_risk value: {reward_risk_str}, treating as loss")
                    is_win = False
                    pnl = -(risk_amount + fee)
            
            return pnl, is_win
            
        except Exception as e:
            logger.error(f"Error calculating PnL for trade: {str(e)}")
            return 0.0, False
    
    def run_backtest(self, trades_df: pd.DataFrame) -> Tuple[Optional[pd.DataFrame], BacktestStats]:
        """
        Run backtest simulation on trades.
        
        Returns:
            Tuple of (equity_curve_df, stats)
        """
        if trades_df is None or trades_df.empty:
            logger.error("Cannot run backtest on empty trades")
            return None, BacktestStats()
        
        stats = BacktestStats()
        balance = self.config.initial_capital
        max_equity = self.config.initial_capital
        max_drawdown = 0.0
        
        # Track yearly performance
        yearly_stats = {}
        
        # Track buy/sell specific stats
        buy_wins = 0
        buy_total = 0
        sell_wins = 0
        sell_total = 0
        
        # Build equity curve
        equity_curve = []
        
        logger.info(f"Starting backtest with {len(trades_df)} trades")
        logger.info(f"Initial capital: ${self.config.initial_capital:,.2f}")
        logger.info(f"Risk per trade: {self.config.risk_pct*100:.1f}%")
        logger.info(f"Fee per trade: {self.config.fee_pct*100:.2f}%")
        
        for idx, row in trades_df.iterrows():
            try:
                # Calculate trade PnL
                pnl, is_win = self.calculate_trade_pnl(row, balance)
                
                # Update balance
                balance += pnl
                
                # Track statistics
                stats.total_trades += 1
                if is_win:
                    stats.winning_trades += 1
                else:
                    stats.losing_trades += 1
                
                # Track by trade type
                trade_type = str(row['type']).lower()
                if trade_type == 'buy':
                    buy_total += 1
                    stats.buy_trades += 1
                    if is_win:
                        buy_wins += 1
                elif trade_type == 'sell':
                    sell_total += 1
                    stats.sell_trades += 1
                    if is_win:
                        sell_wins += 1
                
                # Update max equity and drawdown
                if balance > max_equity:
                    max_equity = balance
                
                current_drawdown = (max_equity - balance) / max_equity if max_equity > 0 else 0
                if current_drawdown > max_drawdown:
                    max_drawdown = current_drawdown
                
                # Track yearly stats
                try:
                    year = row['datetime'].year
                    if year not in yearly_stats:
                        yearly_stats[year] = {
                            'trades': 0,
                            'wins': 0,
                            'losses': 0,
                            'pnl': 0.0
                        }
                    yearly_stats[year]['trades'] += 1
                    yearly_stats[year]['wins'] += 1 if is_win else 0
                    yearly_stats[year]['losses'] += 0 if is_win else 1
                    yearly_stats[year]['pnl'] += pnl
                except Exception as e:
                    logger.warning(f"Failed to track yearly stats for trade {idx}: {str(e)}")
                
                # Record equity point
                equity_curve.append({
                    'trade_number': idx + 1,
                    'datetime': row['datetime'],
                    'balance': balance,
                    'pnl': pnl,
                    'is_win': is_win,
                    'trade_type': trade_type
                })
                
            except Exception as e:
                logger.error(f"Error processing trade {idx}: {str(e)}")
                continue
        
        # Calculate final statistics
        stats.final_balance = balance
        stats.total_pnl = balance - self.config.initial_capital
        stats.max_equity = max_equity
        stats.max_drawdown = max_drawdown
        
        # Calculate win rates with zero-division protection
        stats.win_rate = (stats.winning_trades / stats.total_trades * 100) if stats.total_trades > 0 else 0.0
        stats.buy_win_rate = (buy_wins / buy_total * 100) if buy_total > 0 else 0.0
        stats.sell_win_rate = (sell_wins / sell_total * 100) if sell_total > 0 else 0.0
        stats.yearly_stats = yearly_stats
        
        # Create equity curve DataFrame
        equity_df = pd.DataFrame(equity_curve) if equity_curve else None
        
        logger.info(f"Backtest completed: {stats.total_trades} trades processed")
        logger.info(f"Final balance: ${stats.final_balance:,.2f}")
        logger.info(f"Total PnL: ${stats.total_pnl:,.2f} ({stats.total_pnl/self.config.initial_capital*100:.2f}%)")
        
        return equity_df, stats


class ResultsReporter:
    """Handles output and reporting of backtest results."""
    
    @staticmethod
    def save_results(equity_df: pd.DataFrame, stats: BacktestStats, output_file: str) -> bool:
        """Save equity curve to CSV file."""
        try:
            if equity_df is not None and not equity_df.empty:
                equity_df.to_csv(output_file, index=False)
                logger.info(f"Results saved to {output_file}")
                return True
            else:
                logger.warning("No equity curve data to save")
                return False
        except Exception as e:
            logger.error(f"Failed to save results: {str(e)}")
            return False
    
    @staticmethod
    def print_summary(stats: BacktestStats, config: BacktestConfig):
        """Print formatted summary of backtest results."""
        print("\n" + "="*80)
        print("BACKTEST SUMMARY")
        print("="*80)
        
        print(f"\nConfiguration:")
        print(f"  Initial Capital: ${config.initial_capital:,.2f}")
        print(f"  Risk per Trade: {config.risk_pct*100:.1f}%")
        print(f"  Fee per Trade: {config.fee_pct*100:.2f}%")
        print(f"  Threshold: {config.threshold}")
        
        print(f"\nOverall Performance:")
        print(f"  Total Trades: {stats.total_trades}")
        print(f"  Winning Trades: {stats.winning_trades}")
        print(f"  Losing Trades: {stats.losing_trades}")
        print(f"  Win Rate: {stats.win_rate:.2f}%")
        
        print(f"\nTrade Type Breakdown:")
        print(f"  Buy Trades: {stats.buy_trades} (Win Rate: {stats.buy_win_rate:.2f}%)")
        print(f"  Sell Trades: {stats.sell_trades} (Win Rate: {stats.sell_win_rate:.2f}%)")
        
        print(f"\nFinancial Results:")
        print(f"  Final Balance: ${stats.final_balance:,.2f}")
        print(f"  Total PnL: ${stats.total_pnl:,.2f}")
        print(f"  Return: {(stats.total_pnl/config.initial_capital*100):.2f}%")
        print(f"  Max Equity: ${stats.max_equity:,.2f}")
        print(f"  Max Drawdown: {stats.max_drawdown*100:.2f}%")
        
        if stats.yearly_stats:
            print(f"\nYearly Performance:")
            print(f"  {'Year':<8} {'Trades':<10} {'Wins':<8} {'Losses':<8} {'Win Rate':<12} {'PnL':<15}")
            print(f"  {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*12} {'-'*15}")
            
            for year in sorted(stats.yearly_stats.keys()):
                year_data = stats.yearly_stats[year]
                win_rate = (year_data['wins'] / year_data['trades'] * 100) if year_data['trades'] > 0 else 0
                print(f"  {year:<8} {year_data['trades']:<10} {year_data['wins']:<8} "
                      f"{year_data['losses']:<8} {win_rate:<10.2f}% ${year_data['pnl']:>13,.2f}")
        
        print("\n" + "="*80 + "\n")
    
    @staticmethod
    def save_stats_json(stats: BacktestStats, config: BacktestConfig, filename: str = None):
        """Save statistics to JSON file for programmatic access."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_stats_{timestamp}.json"
        
        try:
            output = {
                'config': asdict(config),
                'stats': asdict(stats),
                'timestamp': datetime.now().isoformat()
            }
            
            with open(filename, 'w') as f:
                json.dump(output, f, indent=2, default=str)
            
            logger.info(f"Statistics saved to {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to save statistics JSON: {str(e)}")
            return False


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Production-ready backtesting bot',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        '--threshold',
        type=int,
        default=1,
        help='Threshold value for filtered trades folder'
    )
    
    parser.add_argument(
        '--capital',
        type=float,
        default=10000.0,
        help='Initial capital for backtest'
    )
    
    parser.add_argument(
        '--risk',
        type=float,
        default=0.05,
        help='Risk percentage per trade (0.05 = 5%%)'
    )
    
    parser.add_argument(
        '--fee',
        type=float,
        default=0.005,
        help='Fee percentage per trade (0.005 = 0.5%%)'
    )
    
    parser.add_argument(
        '--folder',
        type=str,
        default='step3_filtered',
        help='Path to filtered trades folder'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output CSV filename (auto-generated if not specified)'
    )
    
    parser.add_argument(
        '--save-json',
        action='store_true',
        help='Save statistics to JSON file'
    )
    
    return parser.parse_args()


def main():
    """Main entry point for the backtesting bot."""
    print("\n" + "="*80)
    print("PRODUCTION BACKTESTING BOT")
    print("="*80 + "\n")
    
    # Parse command-line arguments
    args = parse_arguments()
    
    try:
        # Create configuration
        config = BacktestConfig(
            threshold=args.threshold,
            initial_capital=args.capital,
            risk_pct=args.risk,
            fee_pct=args.fee,
            filtered_folder=args.folder,
            output_file=args.output
        )
        
        logger.info("Configuration validated successfully")
        
        # Load trade data
        loader = TradeDataLoader(config)
        trades_df = loader.load_survived_trades()
        
        if trades_df is None or trades_df.empty:
            logger.error("Failed to load trade data. Exiting.")
            sys.exit(1)
        
        # Run backtest
        engine = BacktestEngine(config)
        equity_df, stats = engine.run_backtest(trades_df)
        
        if equity_df is None:
            logger.error("Backtest failed. Exiting.")
            sys.exit(1)
        
        # Save and report results
        reporter = ResultsReporter()
        reporter.save_results(equity_df, stats, config.output_file)
        reporter.print_summary(stats, config)
        
        if args.save_json:
            reporter.save_stats_json(stats, config)
        
        logger.info("Backtest completed successfully")
        
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
