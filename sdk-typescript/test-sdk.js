const { Nexus } = require('./dist/index.js');

async function test() {
    try {
        // Register a new agent
        console.log('Registering agent...');
        const nexus = await Nexus.register({
            slug: 'ts-sdk-test',
            name: 'TypeScript SDK Test',
            description: 'Testing the TS SDK'
        });

        console.log('Agent registered!');
        const me = await nexus.me();
        console.log('Agent: ' + me.name + ' (' + me.slug + ')');

        // Store memory
        console.log('\nStoring memory...');
        const mem = await nexus.memory.store('greeting', { text: 'Hello from TypeScript!' });
        console.log('Stored: ' + mem.key);

        // Retrieve memory
        const retrieved = await nexus.memory.get('greeting');
        console.log('Retrieved: ' + JSON.stringify(retrieved.value));

        // Search
        console.log('\nSearching...');
        const results = await nexus.memory.search({ query: 'hello greeting' });
        console.log('Found ' + results.length + ' results');
        if (results.length > 0) {
            console.log('Top score: ' + results[0].score.toFixed(2));
        }

        // Register capability
        console.log('\nRegistering capability...');
        const cap = await nexus.capabilities.register({
            name: 'typescript-helper',
            description: 'Helps with TypeScript questions',
            category: 'development'
        });
        console.log('Capability: ' + cap.name);

        // Discover
        console.log('\nDiscovering...');
        const found = await nexus.discover({ query: 'typescript help' });
        console.log('Found ' + found.length + ' capabilities');
        if (found.length > 0) {
            console.log('Top: ' + found[0].agent_name + ' - ' + found[0].capability.name);
        }

        console.log('\n✓ All TypeScript SDK tests passed!');
    } catch (error) {
        console.error('Error:', error.message);
        if (error.response) {
            console.error('Response:', error.response.data);
        }
    }
}

test();
