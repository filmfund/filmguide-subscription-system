// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title Film2Guide3Subscription - Gas Optimized
/// @notice Minimal subscription system for filmmakers
contract Film2Guide3Subscription is Ownable, ReentrancyGuard {
    
    using SafeERC20 for IERC20;
    
    /// @notice Simplified subscription structure
    struct Subscription {
        address subscriber;        // 20 bytes
        uint32 nextPayment;        // 4 bytes (timestamp fits in 32 bits until 2106)
        uint32 createdAt;         // 4 bytes
        bool active;               // 1 byte
    }
    
    /// @notice State variables
    mapping(uint256 => Subscription) public subscriptions;
    mapping(address => uint256[]) public subscriberSubscriptions;
    
    uint256 public nextSubscriptionId = 1;
    uint256 public totalSubscribers = 0;
    
    // PYUSD token address
    IERC20 public immutable pyusdToken;
    
    // Single subscription price: $8/month
    uint256 public constant SUBSCRIPTION_PRICE = 10 * 10**18;
    
    // Revenue split: 20% platform, 80% filmmakers (simplified)
    uint256 public constant PLATFORM_FEE = 2000; // 20% in basis points
    uint256 public constant FILMMAKER_FEE = 8000; // 80% in basis points
    
    /// @notice Events (minimal)
    event SubscriptionCreated(uint256 indexed subscriptionId, address indexed subscriber);
    event PaymentProcessed(uint256 indexed subscriptionId, address indexed subscriber);
    event SubscriptionCancelled(uint256 indexed subscriptionId, address indexed subscriber);
    
    /// @notice Errors
    error SubscriptionNotFound();
    error SubscriptionNotActive();
    error PaymentNotDue();
    error InvalidSubscription();
    
    /// @notice Constructor
    constructor(address _pyusdToken) {
        pyusdToken = IERC20(_pyusdToken);
    }
    
    /// @notice Create a new subscription
    function createSubscription() external nonReentrant {
        uint256 subscriptionId = nextSubscriptionId++;
        
        // Create subscription 
        subscriptions[subscriptionId] = Subscription({
            subscriber: msg.sender,
            nextPayment: uint32(block.timestamp + 30 days),
            createdAt: uint32(block.timestamp),
            active: true
        });
        
        // Add to subscriber's subscriptions
        subscriberSubscriptions[msg.sender].push(subscriptionId);
        
        // Process initial payment
        _processPayment(subscriptionId);
        
        totalSubscribers++;
        
        emit SubscriptionCreated(subscriptionId, msg.sender);
    }
    
    /// @notice Process subscription payment
    function processPayment(uint256 _subscriptionId) external nonReentrant {
        Subscription storage sub = subscriptions[_subscriptionId];
        if (sub.subscriber == address(0)) revert SubscriptionNotFound();
        if (!sub.active) revert SubscriptionNotActive();
        if (block.timestamp < sub.nextPayment) revert PaymentNotDue();
        
        _processPayment(_subscriptionId);
    }
    
    /// @notice Internal payment processing
    function _processPayment(uint256 _subscriptionId) internal {
        Subscription storage sub = subscriptions[_subscriptionId];
        
        // Transfer PYUSD from subscriber to contract
        pyusdToken.safeTransferFrom(sub.subscriber, address(this), SUBSCRIPTION_PRICE);
        
        // Update subscription 
        sub.nextPayment = uint32(block.timestamp + 30 days);
        
        // Distribute revenue 
        uint256 platformAmount = (SUBSCRIPTION_PRICE * PLATFORM_FEE) / 10000;
        
        // Transfer platform fee to owner
        if (platformAmount > 0) {
            pyusdToken.safeTransfer(owner(), platformAmount);
        }
        
        // Remaining amount stays in contract for filmmaker distribution
        
        emit PaymentProcessed(_subscriptionId, sub.subscriber);
    }
    
    /// @notice Cancel subscription
    function cancelSubscription(uint256 _subscriptionId) external {
        Subscription storage sub = subscriptions[_subscriptionId];
        if (sub.subscriber == address(0)) revert SubscriptionNotFound();
        if (sub.subscriber != msg.sender) revert InvalidSubscription();
        
        sub.active = false;
        
        emit SubscriptionCancelled(_subscriptionId, msg.sender);
    }
    
    /// @notice Get subscriber's active subscriptions
    function getSubscriberSubscriptions(address _subscriber) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return subscriberSubscriptions[_subscriber];
    }
    
    /// @notice Get subscription details
    function getSubscription(uint256 _subscriptionId) 
        external 
        view 
        returns (Subscription memory) 
    {
        return subscriptions[_subscriptionId];
    }
    
    /// @notice Withdraw PYUSD (owner only)
    function withdrawPYUSD() external onlyOwner {
        pyusdToken.safeTransfer(owner(), pyusdToken.balanceOf(address(this)));
    }
}