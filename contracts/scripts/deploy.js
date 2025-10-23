const hre = require("hardhat");

async function main() {
    // PYUSD token address on Sepolia testnet

    const PYUSD_ADDRESS = "0x..."; //actual PYUSD address on Sepolia

    console.log("Deploying Film2Guide3Subscription...");

    const Film2Guide3Subscription = await hre.ethers.getContractFactory("Film2Guide3Subscription");
    const subscription = await Film2Guide3Subscription.deploy(PYUSD_ADDRESS);

    await subscription.waitForDeployment();

    const contractAddress = await subscription.getAddress();

    console.log("Film2Guide3Subscription deployed to:", contractAddress);
    console.log("PYUSD Token address:", PYUSD_ADDRESS);
    console.log("Subscription price: 10 PYUSD per month");
    console.log("Revenue split: 20% platform, 70% filmmakers, 10% festival fund");

    // Verify contract on Etherscan
    if (hre.network.name === "sepolia") {
        console.log("Waiting for block confirmations...");
        await subscription.deploymentTransaction().wait(6);

        console.log("Verifying contract on Etherscan...");
        try {
            await hre.run("verify:verify", {
                address: contractAddress,
                constructorArguments: [PYUSD_ADDRESS],
            });
            console.log("Contract verified successfully!");
        } catch (error) {
            console.log("Verification failed:", error.message);
        }
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
